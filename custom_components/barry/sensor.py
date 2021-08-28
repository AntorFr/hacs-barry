"""Sensor platform for the Flipr's pool_sensor."""
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    CURRENCY_EURO,
    DEVICE_CLASS_MONETARY,
    ATTR_ATTRIBUTION

)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import StateType
from homeassistant.config_entries import ConfigEntry

from homeassistant.util import Throttle

from homeassistant.util.dt import as_local, utcnow

from datetime import timedelta

from typing import Any

from . import BarryEntity

from .const import ATTRIBUTION, DOMAIN
import logging
_LOGGER = logging.getLogger(__name__)

SENSORS = {
    "kWh_prices": {
        "unit": f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        "icon": "mdi:currency-eur",
        "name": "kWh total price",
        "device_class": DEVICE_CLASS_MONETARY,
    }
}

SCAN_INTERVAL = timedelta(seconds=120)


async def async_setup_entry(
        hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities) -> bool:
    """Defer sensor setup to the shared sensor module."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors_list = []
    for sensor in SENSORS:
        sensors_list.append(BarrySensor(coordinator, sensor))

    async_add_entities(sensors_list, True)
    return True


class BarrySensor(BarryEntity, Entity):
    """Sensor representing FliprSensor data."""

    @property
    def name(self) -> str:
        """Return the name of the particular component."""
        return f"Barry {SENSORS[self.info_type]['name']}"

    @property
    def state(self) -> StateType:
        """State of the sensor."""
        return self.get_data(self.info_type, utcnow())

    @property
    def device_class(self) -> str:
        """Return the device class."""
        return SENSORS[self.info_type]["device_class"]

    @property
    def icon(self) -> str:
        """Return the icon."""
        return SENSORS[self.info_type]["icon"]

    @property
    def unit_of_measurement(self) -> str:
        """Return unit of measurement."""
        return SENSORS[self.info_type]["unit"]

    @property
    def device_state_attributes(self) -> dict[str, Any]:
        """Return device attributes."""
        return {self.info_type: {
            as_local(h).isoformat(): data
            for h, data in self.get_data(self.info_type).items()
        },
            ATTR_ATTRIBUTION: ATTRIBUTION}

    @Throttle(SCAN_INTERVAL)
    def update(self):
        """Update device state."""
        try:
            _LOGGER.debug("Barry - Update device state")
            self._attr_state = self.coordinator.get_data(
                self.info_type, utcnow())
            self._attr_extra_state_attributes.update = {
                self.info_type: {
                    as_local(h).isoformat(): data
                    for h, data in self.get_data(self.info_type).items()
                }
            }
        except KeyError as error:
            _LOGGER.error("Missing curent value in values: %s: %s",
                          self.info_type, error)
