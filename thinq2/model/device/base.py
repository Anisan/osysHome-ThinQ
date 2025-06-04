from marshmallow_dataclass import dataclass

from plugins.ThinQ.thinq2.schema import CamelCaseSchema


@dataclass(base_schema=CamelCaseSchema)
class DeviceStatic:
    device_type: int
    country_code: str


@dataclass(base_schema=CamelCaseSchema)
class Device:
    timestamp: float
    static: DeviceStatic
