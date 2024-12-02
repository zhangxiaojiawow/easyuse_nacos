import nacos
import os
import logging
from pydantic import create_model, BaseModel, Field
import json


class NacosConfigProperty:
    """
    descriptor for nacos config value.
    """

    def __init__(self, default_value=None, group='DEFAULT_GROUP', no_snap_shot=None):
        self.default_value = default_value
        self.group = group
        self.attr_name = None
        self._nacos_client = None
        self.no_snap_shot = no_snap_shot
        self.dynamic_model = None
        self.should_json_data = False

    def __get__(self, instance, owner):
        """
        when there has no config value in server or encounter error, return default value
        """
        try:
            val = self._get_nacos_client().get_config(self.attr_name, self.group, no_snapshot=self.no_snap_shot)
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
            return nacos.NacosClient(os.environ.get('NACOS_SERVER'),
                                     namespace=os.environ.get('NACOS_NAMESPACE_ID'),
                                     ak=os.environ.get('NACOS_AK'),
                                     sk=os.environ.get('NACOS_SK'),
                                     username=os.environ.get('NACOS_USERNAME'),
                                     password=os.environ.get('NACOS_PASSWORD'))
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
            client = nacos_client if nacos_client else nacos.NacosClient(server_address, namespace=namespace_id,
                                                                         username=username, password=password,
                                                                         ak=ak, sk=sk)
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




