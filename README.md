# ThinQ - LG ThinQ Integration

![ThinQ Icon](static/ThinQ.png)

Integration with LG ThinQ v2 protocol for controlling and monitoring LG smart home devices.

## Description

The `ThinQ` module provides integration with LG ThinQ v2 protocol for the osysHome platform. It enables control and monitoring of LG smart home devices including air conditioners, washing machines, refrigerators, and more.

## Main Features

- ✅ **ThinQ v2 Protocol**: Native LG ThinQ v2 API support
- ✅ **Device Control**: Control LG smart devices
- ✅ **State Monitoring**: Real-time device state monitoring
- ✅ **MQTT Integration**: MQTT-based real-time updates
- ✅ **Property Linking**: Link device states to object properties
- ✅ **Method Linking**: Link device commands to object methods
- ✅ **Search Integration**: Search devices and states

## Admin Panel

The module provides an admin interface for:
- Viewing ThinQ devices
- Configuring device settings
- Managing device states
- Linking states to properties

## Configuration

- **API Key**: LG ThinQ API key (Personal Access Token)
- **Country**: Country code (default: RU)
- **Client ID**: Unique client identifier

## Getting API Key

1. Visit https://connect-pat.lgthinq.com
2. Log in to ThinQ account
3. Click "ADD NEW TOKEN"
4. Enter token name
5. Select features
6. Click "CREATE TOKEN"
7. Copy the generated token

## Usage

### Adding Device

1. Navigate to ThinQ module
2. Configure API key in settings
3. Devices discovered automatically
4. Link device states to object properties

## Technical Details

- **Protocol**: LG ThinQ v2 API
- **Library**: thinqconnect
- **MQTT**: Real-time state updates via MQTT
- **Async Support**: Asyncio-based operations

## Version

Current version: **1.0**

## Category

Devices

## Actions

The module provides the following actions:
- `cycle` - Background device monitoring
- `search` - Search devices and states

## Requirements

- Flask
- thinqconnect
- SQLAlchemy
- osysHome core system

## Author

Eraser

## License

See the main osysHome project license

