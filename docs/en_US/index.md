# Dreame plugin

The **Dreame** plugin lets Jeedom control **Dreame** robot vacuums and mops through the **Dreamehome** cloud (the service used by the Dreamehome mobile app).

Features:

- start, pause, stop, return to dock, locate;
- suction level, water volume and cleaning mode (vacuum, mop or both);
- base station: auto-empty, mop washing and drying;
- robot state, error, battery, charging, last cleaning time and area;
- station status (clean/dirty water tanks, dust bag);
- consumables (brushes, filter, sensors, mop pads…) with reset commands;
- volume, child lock, carpet boost and do-not-disturb.

State changes are received **in real time**; a fallback poll runs every 60 s when idle and every 15 s while cleaning. Commands are created **according to your model's capabilities**.

## Compatibility

Robots bound to a **Dreamehome** account. Validated on a **Dreame L40 Ultra**. Robots bound only to **Xiaomi Mi Home** are not supported.

## Requirements

Jeedom 4.4+, Debian 11/12, a Dreamehome account (e-mail and password) and Internet access.

## Setup

1. Install and enable the plugin, then install the **dependencies**.
2. In the plugin configuration enter the Dreamehome e-mail, password and **account region** (Europe for European accounts). The daemon starts automatically.
3. In **Plugins → Connected objects → Dreame** click **Synchronize**: robots are created automatically.

## Troubleshooting

Check **Analysis → Health** and the `dreame_daemon` log. "Login failed" usually means wrong credentials or wrong region. Set the plugin log level to **Debug** before reporting an issue.

This plugin is not developed or endorsed by Dreame. The cloud protocol comes from the open source project [Tasshack/dreame-vacuum](https://github.com/Tasshack/dreame-vacuum) (MIT licence).
