# Smart LD2410 for Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/tinkerborg/homeassistant-smart-ld2410/blob/HEAD/LICENSE)

### WORK IN PROGRESS - don't install this yet!

A Home Assistant integration for the HLK-LD2410 24GHz mmWave presence sensor over Bluetooth.

## Requirements

- Home Assistant with a working Bluetooth adapter or ESPHome Bluetooth proxy
- An HLK-LD2410 in Bluetooth range

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS (category: Integration).
2. Search for **Smart LD2410** and install it.
3. Restart Home Assistant.

### Manual

Copy `custom_components/smart_ld2410` into your Home Assistant `config/custom_components/` directory and restart.

## Setup

The sensor is discovered automatically under **Settings → Devices & Services**, or add it via **Add Integration → Smart LD2410**.

## Development

```sh
uv run --group test pytest
```
