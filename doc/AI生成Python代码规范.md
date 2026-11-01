# AI 生成 Python 业务代码规范

本文面向为 Python-C# RPC Bridge 生成或编写业务模块的 AI。生成代码必须符合本规范；扫描器不支持的写法会导致模块构建失败。规范以当前 `scanner.py` 和 C# 生成器实际支持的能力为准。

## 1. 输出要求

1. 只输出业务模块源码及其确实需要的本地辅助 `.py` 文件，不要修改 `generated/` 下的文件。
2. 业务入口文件放在 `modules/` 下，文件名使用合法 Python 标识符，例如 `order_service.py`。
3. 业务入口只放导入、模块文档字符串、函数和类。不要在模块顶层执行初始化、打印、读写文件或调用业务函数。
4. 所有对 C# 暴露的函数、构造函数参数和实例方法参数/返回值都必须写受支持的类型注解。
5. 函数和方法只负责业务逻辑；避免把未验证的外部输入当作可信数据。
6. 如果需求无法用本规范支持的接口表达，应先说明缺少的桥接能力，不要臆造 C# API 或绕过扫描器约束。

## 2. 允许的模块结构

入口模块顶层允许：

- `import` 和绝对 `from ... import ...`
- 模块文档字符串
- 普通同步函数
- 普通类

示例：

```python
from helpers.text import normalize_text


def normalize(value: str) -> str:
    """Normalize user-provided text."""
    return normalize_text(value)
```

本地静态导入的 `.py` 依赖会递归复制到后端目录，并保留包目录结构。入口业务文件不要使用相对导入。动态导入、运行时才拼出的模块名和第三方包不会由本地依赖收集器自动复制；第三方依赖必须由运行环境或打包配置另行提供。

禁止在入口模块顶层定义变量、常量、类型别名、实例或执行语句；不要使用 `if __name__ == "__main__":`。被导入的辅助模块不经过业务接口扫描，但应保持导入时无副作用。

## 3. 函数与参数

- 必须使用 `def`，不支持 `async def`。
- 每个参数和返回值都必须有类型注解；无返回值使用 `-> None`。
- 不支持装饰器、仅位置参数、`*args` 和 `**kwargs`。
- 默认值必须是标量字面值：字符串、整数、小数或布尔值。不要使用函数调用、变量、列表或字典作为默认值。
- 参数名和函数名必须是合法 Python 标识符；避免 Python 关键字及可能冲突的名称。
- 支持普通参数和关键字专用参数。

```python
def find_item(item_id: int, include_archived: bool = False) -> str:
    """Find an item and return its display name."""
    return str(item_id)
```

单个 `str` 参数的方法在 C# 侧会生成业务字符串重载；原始 JSON 参数入口带 `_json` 后缀。其他参数可直接映射成强类型 C# 参数时，生成器也会提供强类型重载。

## 4. 支持的类型和 C# 映射

| Python 注解                | C# 类型          | 用法                       |
| -------------------------- | ---------------- | -------------------------- |
| `int`                    | `int`          | 整数                       |
| `float`                  | `double`       | 浮点数                     |
| `str`                    | `string`       | 文本                       |
| `bool`                   | `bool`         | 布尔值                     |
| `list`                   | `JsonArray`    | 未声明元素类型的 JSON 数组 |
| `dict`                   | `JsonObject`   | 未声明键值类型的 JSON 对象 |
| `None`（仅返回值）       | `void`         | 无返回值                   |
| `list[int]`              | `int[]`        | 整数数组                   |
| `list[float]`            | `double[]`     | 浮点数组                   |
| `list[str]`              | `string[]`     | 字符串数组                 |
| `list[bool]`             | `bool[]`       | 布尔数组                   |
| `list[dict[str, int]]`   | `JsonObject[]` | JSON 对象数组              |
| `dict[str, int]`         | `JsonObject`   | JSON 对象                  |
| `dict[str, list[float]]` | `JsonObject`   | 值包含浮点数组的 JSON 对象 |

`list[...]` 只支持一维数组，元素可以是受支持的基础类型或 `dict`；不支持 `list[list[T]]` 等多维数组。带元素类型的集合参数可生成强类型 C# 重载；不带元素类型的 `list`/`dict` 参数使用 `string jsonArgs` JSON 入口。返回类型按上表映射。

不支持 `Optional`、联合类型、元组、集合、枚举、自定义类、`Any`、非字符串字典键及其他泛型类型。不要写 `list[None]`、`dict[int, str]` 或 `list[tuple]`。

## 5. 类与实例方法

- 只支持普通类：不使用继承、元类、类装饰器或方法装饰器。
- 类体中只能包含类文档字符串、`__init__` 和实例方法；不能声明类变量、属性、嵌套类或静态/类方法。
- 实例方法第一个参数必须为 `self`。所有其余参数及返回值遵循本规范的类型要求。
- 如果定义 `__init__`，返回注解必须为 `-> None`；构造参数只支持 `int`、`float`、`str`、`bool`，默认值为标量字面值。
- 实例方法的文档字符串必须表明它是读取还是写入状态，可使用 `Read`/`Write` 或“读”/“写”。
- 不支持 `__del__`、`close` 或其他双下划线方法。
- 未标注的 Python `self` 成员变量不会成为 C# 属性。可以用 getter/setter 实例方法暴露状态，也可以按下方规则显式导出实例字段。
- 若要让实例字段直接成为 C# 属性，必须在 `__init__` 中给字段显式注解。所有带类型注解的实例字段都会生成可读写 C# 属性；未标注字段不会导出：

```python
class Counter:
    def __init__(self) -> None:
        self.value: int = 0
        self.limit: int = 10
```

此例会生成可读写的 `Value` 和 `Limit` C# 属性。

```python
class Counter:
    """Tracks a counter for one RPC instance."""

    def __init__(self, initial: int = 0) -> None:
        self.value = initial

    def increment(self, amount: int = 1) -> int:
        """Write state by incrementing the counter."""
        self.value += amount
        return self.value

    def get_value(self) -> int:
        """Read state by returning the counter."""
        return self.value
```

## 6. 代码行为限制

- 不使用 `global`、`nonlocal`、`await` 或嵌套异步函数。
- 不导入或使用 `asyncio`、`threading`、`concurrent`、`socket`。
- 不在业务接口实现中创建线程、套接字、显式文件句柄或网络请求；例如避免 `open()`、`socket()`、`urlopen()`。
- 不要向标准输出写日志；标准输出是 RPC 协议通道。需要诊断时使用标准错误。
- RPC 后端按顺序处理请求；耗时函数会阻塞同一进程后续请求。

上述扫描检查只是语法约束，不是安全沙箱。不要用它执行不可信代码；隔离和资源限制必须由操作系统或容器提供。

## 7. 推荐生成模板

AI 应优先按以下结构输出入口文件：

```python
"""Short description of this business module."""

from helpers.validation import validate_value


def process_values(values: list[int]) -> list[int]:
    """Process integer values and return the result."""
    validate_value(values)
    return [value * 2 for value in values]


class ValueProcessor:
    """Processes values with per-instance state."""

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self.calls = 0

    def process(self, values: list[int]) -> list[int]:
        """Write state by recording a call, then process the values."""
        self.calls += 1
        return [value * 2 for value in values]

    def get_calls(self) -> int:
        """Read state by returning the number of calls."""
        return self.calls
```

生成前自检：

1. 入口模块是否只有允许的顶层结构？
2. 暴露的所有参数和返回值是否有支持的注解？
3. 是否误用了装饰器、异步、继承、类变量、文件/网络/线程资源？
4. 每个实例方法文档字符串是否标记读/写状态？
5. 本地依赖是否使用静态导入并与入口模块一起部署？
6. 是否只修改业务源码，而不是手工编辑生成文件？

## 8. 构建和验收

构建前应先运行 Python 测试，再生成并编译目标模块：

```powershell
uv run --locked python -m pytest -q
uv run python -m python_csharp_rpc_bridge.build_tools.build --source-file modules\my_module.py --output-root modules\my_module
```

Debug 部署时，把 `generated\python` 下的全部文件（包括子目录）复制到后端目录，并构建对应模块 DLL。Release 独立发布还需要正确打包 Python 后端及依赖。每次修改业务源码后都要重新生成，并部署同一次构建产出的 DLL 和后端，避免源码哈希不匹配。
