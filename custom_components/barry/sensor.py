"""Sensor platform for the Flipr's pool_sensor."""
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    CURRENCY_EURO,
    DEVICE_CLASS_MONETARY,
    ATTR_ATTRIBUTION

)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
from homeassistant.util.dt import as_local

from datetime import timedelta

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


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Defer sensor setup to the shared sensor module."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors_list = []
    for sensor in SENSORS:
        sensors_list.append(BarrySensor(coordinator, sensor))

    async_add_entities(sensors_list, True)


class BarrySensor(BarryEntity, Entity):
    """Sensor representing FliprSensor data."""

    @property
    def name(self):
        """Return the name of the particular component."""
        return f"Barry {SENSORS[self.info_type]['name']}"

    @property
    def state(self):
        """State of the sensor."""
        return self.coordinator.getData(self.info_type,self.coordinator.client.now)["price"]

    @property
    def device_class(self):
        """Return the device class."""
        return SENSORS[self.info_type]["device_class"]

    @property
    def icon(self):
        """Return the icon."""
        return SENSORS[self.info_type]["icon"]

    @property
    def unit_of_measurement(self):
        """Return unit of measurement."""
        return SENSORS[self.info_type]["unit"]

    @property
    def device_state_attributes(self):
        """Return device attributes."""
        return {self.info_type: {
                        as_local(info["start_date"]).isoformat(): info["price"]
                        for info in self.coordinator.data[self.info_type]
                    },
                ATTR_ATTRIBUTION: ATTRIBUTION}

    @Throttle(SCAN_INTERVAL)
    def update(self):
        """Update device state."""
        try:
            _LOGGER.debug("Barry - Update device state")
            self._attr_state = self.coordinator.getData(self.info_type,self.coordinator.client.now)["price"]
            self._attr_extra_state_attributes.update = {
                self.info_type: {
                    as_local(info["start_date"]).isoformat(): info["price"]
                    for info in self.coordinator.data[self.info_type]
                }
            }
        except KeyError as error:
            _LOGGER.error("Missing curent value in values: %s: %s",
                          self.info_type, error)
