from .base import Device
from .laundry import LaundryDevice
from .fridge import FridgeDevice
from .airconditioner import AirConditioner

device_types = {
    101: FridgeDevice,
    201: LaundryDevice,
    202: LaundryDevice,
    401: AirConditioner,
}
