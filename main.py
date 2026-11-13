"""Decky Loader entry point for HexDeck.

Decky imports this file and calls the ``Plugin`` methods from its asyncio
loop; the frontend reaches them with ``callable(...)`` from ``@decky/api``.
The work happens in ``py_modules/hexdeck`` (which Decky puts on
``sys.path``); every blocking call runs in a worker thread so Decky's loop
never waits on Hex.
"""

import asyncio
import logging
import os
import sys

import decky  # provided by Decky Loader

sys.path.insert(0, os.path.join(decky.DECKY_PLUGIN_DIR, "py_modules"))

from hexdeck.core import HexDeck  # noqa: E402

# The package's loggers (hexdeck.core, hexdeck.service, ...) write to Decky's
# plugin log.
_package_logger = logging.getLogger("hexdeck")
_package_logger.handlers = list(decky.logger.handlers)
_package_logger.setLevel(logging.INFO)
_package_logger.propagate = False


class Plugin:
    deck: HexDeck = None
    loop: asyncio.AbstractEventLoop = None

    async def _main(self):
        Plugin.loop = asyncio.get_running_loop()

        def emit(event, payload):
            asyncio.run_coroutine_threadsafe(decky.emit(event, payload), Plugin.loop)

        Plugin.deck = HexDeck(decky.DECKY_PLUGIN_SETTINGS_DIR, decky.DECKY_PLUGIN_LOG_DIR, emit)
        Plugin.deck.start()
        decky.logger.info("HexDeck started")

    async def _unload(self):
        if Plugin.deck is not None:
            await asyncio.to_thread(Plugin.deck.stop)
            Plugin.deck = None
        decky.logger.info("HexDeck stopped")

    async def _uninstall(self):
        # Hex itself, its models and settings belong to the user and stay.
        pass

    # -- RPC -------------------------------------------------------------------

    @staticmethod
    async def _call(method, *args):
        try:
            result = await asyncio.to_thread(getattr(Plugin.deck, method), *args)
        except Exception as error:
            decky.logger.exception("%s failed", method)
            return {"ok": False, "error": str(error)}
        return result if isinstance(result, dict) or result is None else {"ok": True, "value": result}

    async def get_state(self):
        return await self._call("get_state")

    async def set_config(self, key, value):
        try:
            return {"ok": True, **(await asyncio.to_thread(Plugin.deck.set_config, key, value))}
        except ValueError as error:
            return {"ok": False, "error": str(error)}

    async def list_models(self):
        return await self._call("list_models")

    async def select_model(self, model_id, language=""):
        return await self._call("select_model", model_id, language)

    async def remove_model(self, model_id):
        return await self._call("remove_model", model_id)

    async def cancel_model_download(self):
        return await self._call("cancel_model_download")

    async def get_hex_settings(self):
        return await self._call("get_hex_settings")

    async def set_hex_setting(self, key, value):
        return await self._call("set_hex_setting", key, value)

    async def install_hex(self):
        return await self._call("install_hex")

    async def take_over_hex(self):
        return await self._call("take_over_hex")

    async def restart_hex(self):
        return await self._call("restart_hex")

    async def test_dictation(self, seconds=4):
        return await self._call("test_dictation", seconds)

    async def start_binding_capture(self):
        return await self._call("start_binding_capture")

    async def get_binding_capture(self):
        return await self._call("get_binding_capture")

    async def cancel_binding_capture(self):
        return await self._call("cancel_binding_capture")
