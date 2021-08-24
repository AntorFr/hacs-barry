"""The Flipr integration."""
from __future__ import annotations

import asyncio
from datetime import (
    timezone, datetime, timedelta
    )
import logging
from time import time
from typing import Dict, List

from async_timeout import timeout
from barry_energy import BarryEnergyAPI, PriceArea
from homeassistant.config_entries import ConfigEntry

from homeassistant.core import HomeAssistant

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed
)

from .const import (
    CONF_TOKEN,
    CONF_ZONE,
    CONF_MPID,
    DOMAIN,
    API_TIMEOUT,
    NAME
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: Dict) -> bool:
    """Set up the Barry component."""
    # Make sure coordinator is initialized.
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Barry from a config entry."""
    _LOGGER.debug("async_setup_entry starting")

    coordinator = BarryDataUpdateCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(
                    entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class BarryDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to hold Barry data retrieval."""

    def __init__(self, hass, entry):
        """Initialize."""
        token = entry.data[CONF_TOKEN]
        self.zone = entry.data[CONF_ZONE]
        self.mpid = entry.data[CONF_MPID]

        _LOGGER.debug("Config entry values : %s", token)

        # Establishes the connection.
        self.client = BarryEnergyAPI(token)
        self.hass = hass
        self.entry = entry

        super().__init__(
            hass,
            _LOGGER,
            name=f"Barry device update",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        with timeout(API_TIMEOUT):
            try:
                results = await asyncio.gather(
                    self._fetch_kWh_price_data()
                )
                results =  {rtype:results for r in results for rtype,results in r.items()}
                return results
            except Exception as err:
                raise UpdateFailed(err) from err

    async def _fetch_kWh_price_data(self):
        """Fetch latest kWh price data."""
        _LOGGER.debug("Fetching barry kWh price data")



        if (self.data is not None) and ("kWh_prices" in self.data):
            _LOGGER.debug("Reloading historical data")
            prev_results = self.data["kWh_prices"]
            prev_results_start_time = [r["start_date"] for r in prev_results]
            data_to_fetch = [h for h in range(24) if (self.client.now + timedelta(hours=h)).astimezone(timezone.utc) not in prev_results_start_time]
        else:
            _LOGGER.debug("loading all historical data")
            data_to_fetch = range(24)
            prev_results = []

        data_to_fetch = data_to_fetch[:2]


        results = await asyncio.gather(
            *(self.hass.async_add_executor_job(
                self.client.totalkWhPrice,
                self.client.now + timedelta(hours=h),
                self.client.now+timedelta(hours=h+1),
                self.mpid)
              for h in data_to_fetch
              )
        )
        results = [price for prices in results for price in prices]
        results = [*prev_results, *results]
        return {"kWh_prices": results}

    def getData(self,info_type: str,time:datetime):
        """get info_type data at time moment."""
        time =  time.replace(second=0, microsecond=0, minute=0) \
                    .astimezone(timezone.utc)
        for result in self.data[info_type]:
            if result['start_date'] == time:
                return result
        else:
            return None

class BarryEntity(CoordinatorEntity):
    """Implements a common class elements representing the Flipr component."""

    def __init__(self, coordinator: BarryDataUpdateCoordinator, info_type: str ):
        """Initialize Flipr sensor."""
        super().__init__(coordinator)
        self.mpid = coordinator.mpid
        self.info_type = info_type
        self._unique_id = "barry_{mpid:.5}_{info_type}".format(
            mpid=self.mpid, info_type=self.info_type)

    @property
    def device_info(self):
        """Define device information global to entities."""
        return {
            "identifiers": {
                (DOMAIN, self.mpid)
            },
            "name": "{} - {:.5}".format(NAME,self.mpid)
        }

    @ property
    def unique_id(self):
        """Return a unique id."""
        return self._unique_id

