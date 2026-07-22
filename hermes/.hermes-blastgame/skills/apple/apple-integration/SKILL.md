---
name: apple-integration
description: "Apple ecosystem integration: Notes, Reminders, FindMy, iMessage — macOS-only tools."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [apple, macos, ios, notes, reminders, findmy, imessage]
---

# Apple Ecosystem Integration

All Apple ecosystem skills require macOS. They are unavailable on Linux/Windows hosts.

## Available Tools (macOS only)

- **Apple Notes** — Read, search, create, edit notes in the Apple Notes app
- **Apple Reminders** — Manage reminders (lists, tasks, completion)
- **FindMy** — Locate Apple devices and people via Find My network
- **iMessage** — Send and receive iMessages from the terminal

## Usage Notes

These tools rely on macOS-specific frameworks (AppleScript, CoreLocation, Message.framework) that do not exist on other platforms.
