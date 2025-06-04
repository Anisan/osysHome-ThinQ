from marshmallow_dataclass import dataclass

from plugins.ThinQ.thinq2.schema import CamelCaseSchema


@dataclass(base_schema=CamelCaseSchema)
class Route:
    api_server: str
    mqtt_server: str
