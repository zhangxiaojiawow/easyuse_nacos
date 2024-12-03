# 欢迎使用 EasyUse Nacos

## EasyUse Nacos介绍
easyuse_nacos可帮助你更便捷地从服务端读取配置信息。


## 安装

``` shell title="从pip安装"
pip install easyuse-nacos
```

## 开始使用

* 服务端配置

| Key | Value | Group |
| --- | --- | --- |
| test_key | 1234 | group1 |
| test_json | {"name":"bob","age": 18} | DEFAULT_GROUP |

* 从服务端获取配置

``` py 
from easyuse_nacos import NacosConfig, NacosConfigProperty

class ExampleConfig(NacosConfig, server_address="<your server address>", namespace_id="<your namespace id>"):
    test_key = NacosConfigProperty(group='group1')
    test_json = NacosConfigProperty()

print(ExampleConfig.test_key)
#> 1234
print(ExampleConfig.test_json)
#> {
    "name":"bob",
    "age": 18
}
```

使用easyuse-nacos，从Nacos Server读取配置内容非常简单。我们定义一个继承自`NacosConfig`的数据类，在配置类中定义与需要读取的配置项的data-id同名的属性，同时将配置项所在的group传入NacosConfigProperty中即可, 如果group为默认组（DEFAULT_GROUP）,则可以不用配置。接下来，直接读取对应的类属性就可以！

!!! note
  
    使用类属性和实例属性访问配置项内容，返回结果完全相同。这两种方式完全等价，通常建议直接使用类属性进行访问。
    ```py
    class ExampleConfig(NacosConfig, server_address="<your server address>", namespace_id="<your namespace id>"):
        test_key = NacosConfigProperty(group='group1')
        test_json = NacosConfigProperty()

    print(ExampleConfig.test_key)
    #>1234

    print(ExampleConfig().test_key)
    #>1234
    ```


## 服务端配置

### 全局配置

如果项目内，所有配置项均从一个固定的namespace下读取，可以从环境变量配置服务端信息
``` shell title=".env"
NACOS_SERVER=<your nacos server>
NACOS_NAMESPACE_ID=<your namespace id>
# 服务端nacos.core.sdk.auth.enabled=true时，需配置username和password
NACOS_USERNAME=<username for login nacos server>
NACOS_PASSWORD=<password for login nacos server>
```

### 配置类上进行配置

对于需要从不同服务端或者不同namespace下读取的配置内容，可以在配置类上添加配置信息

* 传入server和namespace

``` py title="在配置类上进行配置"
from easyuse_nacos import NacosConfig, NacosConfigProperty

class ExampleConfig(NacosConfig, server_address="<your server address>", namespace_id="<your namespace id>",
                    username="<your username>", password="<your password>"):
    test_json = NacosConfigProperty()

```

* 传入nacos_client

``` py title="传入nacos_client进行配置"
from easyuse_nacos import NacosConfig, NacosConfigProperty
from nacos import NacosClient

nacos_client = NacosClient(server_addresses='<your server address>',
                           namespace='<your namespace id>')


class ExampleConfig(NacosConfig, nacos_client=nacos_client):
    test_key = NacosConfigProperty(group='group1')
```

### 配置优先级

对于一个配置类，当加载配置项时，将安装以下优先级创建对应的nacos client。

1. 从继承自`NacosConfig`类的子类上读取配置信息，, 如果传入nacos_client，则直接使用该对象。否则，若传入配置信息，使用对应配置信息创建nacos client.

2. 从环境变量配置信息，创建nacos client.

3. 如果配置类和环境变量中都不存在配置信息，则在读取配置内容时抛出异常

## 默认值配置

为了在服务端无配置项获服务端连接异常时，仍然希望返回默认值，可以在配置项上配置默认值。

* 使用静态值作为配置项的默认值

``` py

from easyuse_nacos import NacosConfig, NacosConfigProperty

class ExampleConfig(NacosConfig ):
    not_exist_key = NacosConfigProperty(default_value='default_val')   

print(ExampleConfig.not_exist_key)
#> default_val
```

* 使用无参函数动态返回配置项默认值

对于默认值需要动态创建的配置项，可以传入无参函数作为默认值

```py
from datetime import datetime
from easyuse_nacos import NacosConfig, NacosConfigProperty

class ExampleConfig(NacosConfig ):
    current_datetime = NacosConfigProperty(default_value=lambda : datetime.now())

print(ExampleConfig.current_datetime)
#> 2024-12-02 20:07:52.687404
```

## 属性验证与转化

默认情况下，nacos客户端读取返回的值类型均为字符串类型，在实际使用场景中，需要按需将字符串转化为更具体的类型，如整数、布尔类型等等，非常不便。为了实现字段类型的自动转化，easyuse-nacos引入了pydantic进行属性类型的验证与转化。

``` py
from easyuse_nacos import NacosConfig, NacosConfigProperty
from pydantic import BaseModel

class Person(BaseModel):
    age: int
    name: str


class ExampleConfig(NacosConfig, server_address="<your server>",
                    namespace_id="<your namespace id>",
                    ):
    test_key: int = NacosConfigProperty(group='group1')
    test_json: Person = NacosConfigProperty()

print(ExampleConfig.test_key)
#> 1234
print(ExampleConfig.test_key + 1)
#> 1235
print(ExampleConfig.test_json.age)
#> 18
print(ExampleConfig.test_json.name)
#> bob
```

### 嵌套类型的默认值配置

为了进行嵌套类型的默认值配置，需要利用pydantic的默认值配置功能

``` py

class Person(BaseModel):
    age: int = 22
    name: str = 'jack'


class ExampleConfig(NacosConfig, server_address="<your server>",
                    namespace_id="<your namespace id>",
                    ):
    no_exist_person: Person = NacosConfigProperty(default_value=Person())

print(ExampleConfig.no_exist_person.age)
#> 22
print(ExampleConfig.no_exist_person.name)
#> jack
```

在配置类中，默认值被设置为Person()对象，当服务端不存在对应的配置项时，返回该默认值对象