import nacos
import os
import logging
from pydantic import create_model, BaseModel, Field
import json

nacos_client_pool = {}

def cache_key(server_address, namespace_id, username, password, ak, sk):
    return "".join([server_address, namespace_id, str(username), str(password), str(ak), str(sk)])

class NacosConfigProperty:
    """
    descriptor for nacos config value.
    """

    def __init__(self, default_value=None, group='DEFAULT_GROUP', no_snap_shot=None, read_from_cache=True):
        self.default_value = default_value
        self.group = group
        self.attr_name = None
        self._nacos_client = None
        self.no_snap_shot = no_snap_shot
        self.dynamic_model = None
        self.should_json_data = False
        self.read_from_cache = read_from_cache
        self.cache_value = None

    def register_update_callback(self):
        if self.read_from_cache:
            self._get_nacos_client().add_config_watcher(self.attr_name, self.group, self.update_cache_val)

    def update_cache_val(self, data):
        self.cache_value = data['content']

    


    def __get__(self, instance, owner):
        """
        when there has no config value in server or encounter error, return default value
        """
        try:
            if self.read_from_cache and self.cache_value:
                val = self.cache_value
            else:
                val = self._get_nacos_client().get_config(self.attr_name, self.group, no_snapshot=self.no_snap_shot)
                self.cache_value = val # update cache
        except Exception as e:
            val = None
            logging.error(e)
        if val:
            if self.dynamic_model:
                if self.should_json_data:
                    val = json.loads(val)
                val = self.dynamic_model(**{self.attr_name: val})
                return getattr(val, self.attr_name)
            else:
                return val
        else:
            if self.dynamic_model:
                return getattr(self.dynamic_model(), self.attr_name)
            else:
                return self.get_default_value()

    def get_default_value(self):
        if callable(self.default_value):
            return self.default_value()
        return self.default_value


    def _get_nacos_client(self):
        """
        First use the _nacos_client in the instance, which can be config with the class attribute in NacosConfig.
        If not exist, use the environment variable to create a new nacos client
        """
        if hasattr(self, '_nacos_client') and self._nacos_client:
            return self._nacos_client
        elif os.environ.get('NACOS_SERVER') and os.environ.get('NACOS_NAMESPACE_ID'):
            hash_key = cache_key(os.environ.get('NACOS_SERVER'), os.environ.get('NACOS_NAMESPACE_ID'),
                                    os.environ.get('NACOS_USERNAME'), os.environ.get('NACOS_PASSWORD'),
                                    os.environ.get('NACOS_AK'), os.environ.get('NACOS_SK'))
            if hash_key in nacos_client_pool:
                return nacos_client_pool[hash_key]
            client =  nacos.NacosClient(os.environ.get('NACOS_SERVER'),
                                     namespace=os.environ.get('NACOS_NAMESPACE_ID'),
                                     ak=os.environ.get('NACOS_AK'),
                                     sk=os.environ.get('NACOS_SK'),
                                     username=os.environ.get('NACOS_USERNAME'),
                                     password=os.environ.get('NACOS_PASSWORD'))
            nacos_client_pool[hash_key] = client
            return client

        else:
            raise Exception("""
            there is no nacos client, you can set environment variable NACOS_SERVER NACOS_NAMESPACE_ID NACOS_AK NACOS_SK
            or config it with class decorator @nacos_config
            @nacos_config(SERVER_ADDRESSES, NAMESPACE_ID)
            class MyConfig(NacosConfig):
                test_key = NacosConfigProperty(1, group='group')
            """)

    def __set__(self, instance, value):
        """
        you can only read config values from nacos server. the value can't be set.
        """
        raise AttributeError("Cannot set NacosConfigItem values")

    def __set_name__(self, owner, name):
        self.attr_name = name
        self.register_update_callback()


class NacosConfigMeta(type):
    def __init__(cls, name, bases, attr_dict, **kwargs):
        pass


    def __setattr__(cls, key, value):
        """
        you can only read config values from nacos server. the value can't be set.
        """
        if key in cls.__dict__ and (cls.__dict__[key], NacosConfigProperty):
            raise AttributeError("Cannot set NacosConfigItem values")


class NacosConfig(metaclass=NacosConfigMeta):
    """
    Base class for defining Nacos-like configurations.  Subclasses define attributes,
    All config class should inherit from this class
    """
    def __init_subclass__(cls, nacos_client=None, server_address=None, namespace_id=None,
                          username=None, password=None, ak=None, sk=None) -> None:
        if nacos_client or (server_address and namespace_id):
            if nacos_client:
                client = nacos_client
            else:
                hash_key = cache_key(server_address, namespace_id, username, password, ak, sk)
                if hash_key in nacos_client_pool:
                    client = nacos_client_pool[hash_key] 
                else:
                    client = nacos.NacosClient(server_address, namespace=namespace_id,
                                                                         username=username, password=password,
                                                                         ak=ak, sk=sk)
                    nacos_client_pool[hash_key] = client
            if not hasattr(cls, '__annotations__'):
                return
            anontations = cls.__annotations__ 
            for key, attr in cls.__dict__.items():
                if isinstance(attr, NacosConfigProperty):
                    attr._nacos_client = client
                    if key in anontations:
                        if attr.default_value:
                            if callable(attr.default_value):
                                attr.dynamic_model = create_model('dynamic_model', ** {key: (anontations[key], Field(default_factory = attr.default_value))})
                            else:
                                attr.dynamic_model = create_model('dynamic_model', ** {key: (anontations[key], attr.default_value)})
                        else:
                            attr.dynamic_model = create_model('dynamic_model', ** {key: (anontations[key], ...)})
                        if issubclass(anontations[key], BaseModel):
                            attr.should_json_data = True




