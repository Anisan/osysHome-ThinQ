from uplink import Field, Path, Query, returns
from uplink import get, post, delete, json

from plugins.ThinQ.thinq2.client.base import BaseClient
from plugins.ThinQ.thinq2.model.thinq import (
    DeviceCollection,
    DeviceDescriptor,
    ThinQResult,
    ThinQResultSuccess,
    ThinQPrint,
    IOTRegistration,
    ModelJsonDescriptor,
)

from uplink import response_handler
import pprint

@response_handler
def log_response(response):
    #pprint.pprint(response.content, indent=2)
    return response


@log_response
class ThinQClient(BaseClient):
    """LG ThinQ API client"""

    @get("service/application/dashboard")
    def get_devices(self) -> ThinQResult(DeviceCollection):
        """Retrieves collection of user's registered devices with dashboard data."""

    @returns.json
    @get("service/devices/{device_id}")
    def get_raw_device(self, device_id: Path):
        """Retrieves an individual device without schema"""

    @json
    @post("service/devices/{device_id}/control-sync")
    def control_sync(self, device_id: Path, command: Field, ctrlKey: Field, dataKey: Field, dataValue: Field) -> ThinQPrint():
        """PLACE HOLDER"""

    @get("service/devices/{device_id}")
    def get_device(self, device_id: Path) -> ThinQResult(DeviceDescriptor):
        """Retrieves an individual device"""

    @get("service/application/modeljson")
    def get_model_json_descriptor(
        self, device_id: Query("deviceId"), model_name: Query("modelName")
    ) -> ThinQResult(ModelJsonDescriptor):
        """Retrieves ModelJson descriptor for a device"""

    @get("service/users/client")
    def get_registered(self) -> ThinQResultSuccess():
        """Get client registration status"""

    @post("service/users/client")
    def register(self) -> ThinQResultSuccess():
        """Register client ID"""

    @delete("service/users/client")
    def deregister(self) -> ThinQResultSuccess():
        """Deregister client ID"""

    @json
    @post("service/users/client/certificate")
    def register_iot(self, csr: Field) -> ThinQResult(IOTRegistration):
        """Register an IoT/MQTT session, given a csr"""
