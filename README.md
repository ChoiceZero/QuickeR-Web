
# QuickeR-Web

QuickeR-Web is a platform that lets you create QR codes but without accounts, limits, ads or purchases. It also doesn't collect any personal data, analytics, telemetry or other kind of info. It was primarily created out of pure spite, as most other websites have shitty practices to get the most revenue out of users. Besides, the code has mostly been written by hand, about a 15% of the entire project has been written by AI.



## Features

- Cross platform.
- Creates QRs from these types:

| Type                          | Support   |
| ----------------------------- | --------- |
| Plain text                    | ✅        |
| URL/Link                      | ✅        |
| Social Media & Messenger      | ❌        |
| Wifi                          | ✅        |
| Email                         | ✅        |
| SMS                           | ✅        |
| Phone number                  | ✅        |
| Email                         | ✅        |
| Location                      | ✅        |
| Event                         | ✅        |

- Allows to place logos in the center of the QR.
- Allows to change the colors of the QRs.

> [!WARNING] 
> Due to c based tools (such as OpenCV or Pyztools) not being supported on WASM, color checking is not available.

- Has a preview that updates on every change.
- Downloads the codes.
- Has a summary view before downloading the QR code.
- Uses a Material3-like user interface.
## Tech Stack

**Python moules:** Flet, Qrcode, Pillow and other libraries that base Python includes.

**Actually running the code:** Flutter, Dart


## License

[MIT](https://choosealicense.com/licenses/mit/)

## Run the app

### flet

Run as a desktop app:

```bash
flet run
```

Run recursively as a desktop app:

```bash
flet run --recursive
```

Run as a web app:

```bash
flet run --web
```

Run as an android app:

```bash
flet run --android
```

### uv

Run as a desktop app:

```bash
uv run flet run
```

Run recursively as a desktop app:
```bash
uv run flet run --recursive
```

Run as a web app:

```bash
uv run flet run --web
```

Run as an android app:

```bash
uv run flet run --android
```

For more details on running the app, refer to the [Getting Started Guide](https://flet.dev/docs/).

## Build the app

### Android

```bash
flet build apk -v
```

For more details on building and signing `.apk` or `.aab`, refer to the [Android Packaging Guide](https://flet.dev/docs/publish/android/).

### iOS

```bash
flet build ipa -v
```

For more details on building and signing `.ipa`, refer to the [iOS Packaging Guide](https://flet.dev/docs/publish/ios/).

### macOS

```bash
flet build macos -v
```

For more details on building macOS package, refer to the [macOS Packaging Guide](https://flet.dev/docs/publish/macos/).

### Linux

```bash
flet build linux -v
```

For more details on building Linux package, refer to the [Linux Packaging Guide](https://flet.dev/docs/publish/linux/).

### Windows

```bash
flet build windows -v
```

For more details on building Windows package, refer to the [Windows Packaging Guide](https://flet.dev/docs/publish/windows/).

### Web

```bash
flet build web -v
```

For more details on building Web app, refer to the [Web Packaging Guide](https://flet.dev/docs/publish/web/).


## Authors

- [@ChoiceZero](https://www.github.com/ChoiceZero)


## Related

A desktop app is also available for Linux, Windows and Android.

[Desktop app repository (QuickeR)](https://github.com/ChoiceZero/QuickeR)

