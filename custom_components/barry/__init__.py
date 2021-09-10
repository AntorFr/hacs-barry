"""The Flipr integration."""
from __future__ import annotations
import asyncio
from datetime import (
    timezone, datetime, timedelta, date
)
import logging
import traceback

from typing import Dict, Generator

from async_timeout import timeout
from barry_energy import BarryEnergyAPI, PriceArea
from homeassistant.config_entries import ConfigEntry

from homeassistant.helpers.typing import ConfigType

from homeassistant.core import HomeAssistant

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed
)
from homeassistant.util.dt import utcnow,now , start_of_local_day, as_local

from .const import (
    CONF_TOKEN,
    CONF_ZONE,
    CONF_MPID,
    CONF_CURRENCY,
    CONF_REFRESH_HOUR,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    API_TIMEOUT,
    API_BATCH_SIZE,
    NAME
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=CONF_SCAN_INTERVAL)


PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
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
        self.currency = entry.data[CONF_CURRENCY]

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
                    self.async_fetch_kWh_price_data()
                )
                results = {rtype: results for r in results for rtype,
                           results in r.items()}
                return results
            except Exception as err:
                _LOGGER.error(
                    ("error loading barry data: {}").format(traceback.format_exc()))
                raise UpdateFailed(err) from err

    async def async_fetch_kWh_price_data(self) -> dict:
        """Fetch latest kWh price data."""
        _LOGGER.debug("Fetching barry kWh price data")

        if (self.data is not None) and ("kWh_prices" in self.data):
            # remove result older than today
            prev_results = {date: price for date, price
                            in self.data["kWh_prices"].items()
                            if date >= start_of_local_day()}
        else:
            prev_results = {}

        if now().hour >= CONF_REFRESH_HOUR:
            # tomorrow prices are available
            end_time = start_of_local_day()+timedelta(days=2)
        else:
            end_time = start_of_local_day()+timedelta(days=1)

        data_to_fetch = self.hourly_iterator(end_time, prev_results.keys())
        data_to_fetch = list(data_to_fetch)[:API_BATCH_SIZE]

        results = await asyncio.gather(
            *(self.hass.async_add_executor_job(
                self.hourly_kwh_price, h)
              for h in data_to_fetch
              )
        )
        results = {dt: price for r in results for dt, price in r.items()}
        results = {**prev_results, **results}
        return {"kWh_prices": results}

    def hourly_kwh_price(self, dt: datetime = None):
        if (dt is None):
            dt = self.client.now
        return {dt: self.client.hourlykWhPrice(dt, self.mpid)}

    def hourly_delta(self, delta_hour: timedelta):
        return self.client.now.replace(tzinfo=timezone.utc) + timedelta(hours=delta_hour)

    def hourly_range(self, range: list, exclusion: list = []) -> list:
        """get hourly datetime range data from now to end of range."""
        return [self.hourly_delta(h) for h in range if self.hour_delta(h) not in exclusion]

    def hourly_iterator(self, end_time: datetime, exclusion: list = []) -> Generator:
        """get hourly datetime iterator data for now to end_time."""
        start_time = start_of_local_day().astimezone(timezone.utc)
        end_time = end_time.astimezone(timezone.utc)

        # always start with curent time
        now = self.client.now.replace(tzinfo=timezone.utc)
        if now not in exclusion:
            yield now
        while end_time > start_time:
            if (start_time not in exclusion) and (start_time != now):
                yield start_time
            start_time = start_time + timedelta(hours=1)


class BarryEntity(CoordinatorEntity):
    """Implements a common class elements representing the Flipr component."""

    def __init__(self, coordinator: BarryDataUpdateCoordinator, info_type: str):
        """Initialize Flipr sensor."""
        super().__init__(coordinator)
        self.mpid = coordinator.mpid
        self.currency = coordinator.currency
        self.info_type = info_type
        self._unique_id = "barry_{mpid:.5}_{info_type}".format(
            mpid=self.mpid, info_type=self.info_type)

    @ property
    def device_info(self):
        """Define device information global to entities."""
        return {
            "identifiers": {
                (DOMAIN, self.mpid)
            },
            "name": "{} - {:.5}".format(NAME, self.mpid)
        }

    @ property
    def unique_id(self):
        """Return a unique id."""
        return self._unique_id

    def get_data(self, info_type: str, time: datetime = None):
        """get info_type data at time moment."""
        if info_type not in self.coordinator.data:
            return None

        data = self.coordinator.data[info_type]
        if time is None:
            return data

        time = time.replace(second=0, microsecond=0,
                            minute=0).astimezone(timezone.utc)

        if time in data.keys():
            return data[time]
        else:
            return None

    def get_day_data(self, info_type: str, dt_or_d: date | datetime | None = None) -> dict:
        """get info_type data at for today."""
        start_day = start_of_local_day(dt_or_d)
        results = self.get_data(info_type)
        return {dt: data for dt, data in results.items() if (dt >= start_day and dt < start_day+timedelta(hours=24))}

    def attr_day_data(self, dt_or_d: date | datetime | None = None) -> dict:
        """format day data per hour to be displayed in attributes """
        return {as_local(h).hour: data for h, data in self.get_day_data(self.info_type, dt_or_d).items()}

    def current_frame_data(self):
        """ display the curent frame (order) of day_data or None if day data not already loaded"""
        day_data = self.get_day_data(self.info_type)
        day_data = [d for d in sorted(day_data.values())]
        curent_data = self.state

        try:
            return day_data.index(curent_data)
        except ValueError as error:
            _LOGGER.error("Missing curent value in values: %s: %s",
                          curent_data, error)
            return None
