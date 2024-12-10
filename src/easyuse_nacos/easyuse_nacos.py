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
    为了简化从Nacos服务端读取配置内容的操作,使用描述符对象提供的协议,实现Nacos配置项读取。
    
    该描述符对象配置支持以下功能：
    1. 支持默认值配置，包括值类型与可调用对象类型. 如果默认值为一个可调用对象，则当服务端不存在该配置项时，返回可调用对象调用返回值
    2. 支持配置group，默认值为"DEFAULT_GROUP"
    3. 支持配置no_snap_shot, 该值将在调用nacos_client.get_config方法时传入
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
        raise AttributeError("Cannot set NacosConfigItem values")

    def __set_name__(self, owner, name):
        self.attr_name = name
        self.register_update_callback()


class NacosConfigMeta(type):
    """该元类被设计用来限制实例类中部分属性不可修改

    对于管理Nacos配置项的类(继承自NacosConfig类), 每一个Nacons配置项对应一个类型为NacosConfigProperty描述符的类属性。
    为了防止用户错误的更改对应的类属性,造成后续无法读取nacos配置,需要限制用户无法设置类型为NaconsConfigProperty的字段。
    当用户尝试错误设置类型为NaconsConfigProperty类型的属性时, 将抛出异常。
    """
    def __init__(cls, name, bases, attr_dict, **kwargs):
        pass


    def __setattr__(cls, key, value):
        """ 禁止设置类型为NacosConfigProperty类型的属性, 保持该类型属性永远为只读。

        Arguments:
            key -- 属性名称
            value -- 属性值

        Raises:
            AttributeError: 尝试设置类型为NaconsConfigProperty的类属性，抛出异常
        """
        if key in cls.__dict__ and isinstance(cls.__dict__[key], NacosConfigProperty):
            raise AttributeError("Cannot set attribute with type NacosConfigProperty")

class NacosConfig(metaclass=NacosConfigMeta):
    """ 所有维护Nacons配置项的类,均需继承NaconsConfig。

    NaconsConfig负责以下工作:
    1. 提供NaconsClient的配置入口。包括以下两种方式
        * 在子类型定义中,传入nacos_client

        >>> from nacos import NacosClient
        >>> nacos_client = NacosClient(server_address='<your address>', namespace='<your namespace>')
        >>> class MyConfig(NacosConfig, nacos_client=nacos_client):
                read_data = NaconsConfigProperty()

        * 在子类定义中,传入server_address, namespace_id, username(可选), password(可选), ak(可选), sk(可选)

        >>> class MyConfig(NaconsConfig, server_address='<your address>', namespace='<your namespace>'):
                read_data = NaconsConfigProperty()

        如果同时传入nacos_client对象和server_address, namespace_id等配置信息,则优先使用nacos_client作为后续读取配置内容的客户端。

    2. 设置每一个NaconsConfigProperty对应的nacos_client, 用于后续读取配置内容

    3. 如果配置字段提供了类型注解信息,根据类型注解信息,创建pydantic BaseModel对象, 添加到NaconsConfigProperty对象中。
       如果NaconsConfigProperty对象维护了对应的BaseModel对象,则后续再读取到配置内容后,将自动进行类型验证与转化， 例如将字符串转化为对应的整数类型。       

       >>> from pydantic import BaseModel
       >>> class Person(BaseModel):
               age: int
               name: str

       >>> class MyConfig(NaconsConfig, server_address='<your address>', namespace='<your namespace>'):
               read_data:int = NaconsConfigProperty()
               admin: Person = NaconsConfigProperty()
       
       在上面的示例子中,read_data配置字段的内容期望是一个可以转化为整数的字符串,admin则对应一个json字符串,包含age和name两个key。

    由于NacosConfigProperty描述符对象的_nacos_client字段(用于访问配置内容的nacos client)和dynamic_model字段(用于进行类型验证
    与转化的BaseModel对象)是在对象初始化之后,根据配置类中的其他配置信息设置的,因此,在__init_subclass__方法中完成这些工作。当MyConfig
    的子类被创建时,将执行__init_subclass__方法。
    
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




