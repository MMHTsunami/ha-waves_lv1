"""Pure-Python, Home-Assistant-agnostic client library for the Waves eMotion LV1.

This package has no dependency on Home Assistant. It owns the OSC codec, the
custom framed-TCP transport, and LAN discovery so the transport layer can be
unit-tested in isolation and reused outside of HA if needed.
"""
