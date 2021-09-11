"""Config flow for Barry integration."""
from typing import List

import datetime
from barry_energy import BarryEnergyAPI, PriceArea
from requests.exceptions import HTTPError, Timeout
import voluptuous as vol

from homeassistant.const import CURRENCY_EURO


from homeassistant import config_entries

from .const import CONF_TOKEN, CONF_ZONE, CONF_MPID, CONF_CURRENCY, CONF_CURRENCY_KRONE
from .const import DOMAIN  # pylint:disable=unused-import

import logging
_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Barry."""

    VERSION = 1

    _token: str = None
    _mpid: dict = None
    _possible_mpid: list[dict] = None

    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self._show_setup_form()

        self._token = user_input[CONF_TOKEN]

        errors = {}
        if not self._mpid:
            try:
                mpids = await self._authenticate_check()
            except HTTPError:
                errors["base"] = "invalid_auth"
            except (Timeout, ConnectionError):
                errors["base"] = "cannot_connect"
            except Exception as exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"
                _LOGGER.exception(exception)

            if not errors and len(mpids) == 0:
                # No Mpid ID found. Tell the user with an error message.
                errors["base"] = "no_mpid_id_found"

            if errors:
                return self._show_setup_form(errors)

            if len(mpids) == 1:
                self._mpid = mpids[0]
            else:
                # If multiple barry found (rare case), we ask the user to choose one in a select box.
                # The user will have to run config_flow as many times as many barry he has.
                self._possible_mpid = mpids
                return await self.async_step_mpid()

        # Check if already configured
        await self.async_set_unique_id(self._mpid)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=self._mpid["address"],
            data={
                CONF_TOKEN: self._token,
                CONF_ZONE: self._mpid["price"],
                CONF_MPID: self._mpid["mpid"],
                CONF_CURRENCY: self._get_currency(self._mpid)
            },
        )

    def _show_setup_form(self, errors=None):
        """Show the setup form to the user."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_TOKEN): str}
            ),
            errors=errors,
        )

    async def async_step_mpid(self, user_input=None):
        """Handle the initial step."""
        if not user_input:
            # Creation of a select with the proposal of MPID  values found by API.
            mpids_for_form = {}
            for mpid in self._possible_mpid:
                mpid_desc = f"Barry - {mpid['address']}"
                mpids_for_form[mpid["mpid"]] = f"{mpid_desc}"

            return self.async_show_form(
                step_id="mpid",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_MPID): vol.All(
                            vol.Coerce(str), vol.In(mpids_for_form)
                        )
                    }
                ),
            )

        # Get chosen mpid.
        for mpid in self._possible_mpid:
            if mpid["mpid"] == user_input[CONF_MPID]:
                self._mpid = mpid
                break

        return await self.async_step_user(
            {
                CONF_TOKEN: self._token,
                CONF_ZONE: self._mpid["price"],
                CONF_MPID: self._mpid["mpid"],
                CONF_CURRENCY: self._get_currency(self._mpid)
            }
        )

    async def _authenticate_check(self):
        """Validate the API Token ."""
        client = BarryEnergyAPI(self._token)
        meteringPoints = await self.hass.async_add_executor_job(self._get_meteringPoints, client)
        mpids = [{"mpid": m["mpid"], "address":m["address"]["line1"],
                  "price":m["priceCode"]} for m in meteringPoints]
        return mpids

    @staticmethod
    def _get_meteringPoints(client):
        return client.meteringPoints

    @staticmethod
    def _get_currency(data):
        return CONF_CURRENCY_KRONE if data.get('country') == 'DK' else CURRENCY_EURO
