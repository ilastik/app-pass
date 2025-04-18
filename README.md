# app-pass

Tool to ensure an `.app` bundle pass the Gatekeeper on MacOS.
Originally to sign the bundle for [ilastik](https://ilastik.org).

Prerequisite: You have built your app, and it runs on your own machine ;).
Problem: You try to sign/notarize but get back many errors and are unsure how to resolve them.

Before you consider using this, you might get away without it by:

#### Doing everything via XCODE** :)

#### Your app is Python-based
 * using [constructor](https://github.com/conda/constructor) if your stack is conda-based. Constructor does ad-hoc signing on install.
 * using something like [briefcase](https://github.com/beeware/briefcase).
 * [encrust](https://github.com/glyph/Encrust) seems also to work.
 * [jaunch](https://github.com/apposed/jaunch).

#### Your app is Java-based
 * Consider using [jaunch](https://github.com/apposed/jaunch), which powers Fiji.

In any case, there are many reasons you can't use one of these alternatives and are left with a working .app that you can not sign.
`app-pass` can help you no matter how you generated the app in the first place.

Tested so far with conda-based python apps, and java apps.

`app-pass` can perform various fixes on binaries, and sign `.app` bundles.
Does not require using a specific way to build your `.app` bundle.
Does not require `.app` being written in a specific language, or framework.

We understand that making changes to the binary that you are distributing should be as transparent as possible.
For this, you can generate an `.sh` file that uses only apple dev tools to manipulate your `.app`.
Any `app-pass` command invoked with `--dry-run` will not make any changes to your app.

## Installation

```
pip install git+https://github.com/ilastik/app-pass.git
```

## Fix/Sign/Notarize workflow

In general the workflow is roughly in these stages:

1) You generate your `.app` bundle.
2) The binaries in your app bundle are fixed, and
3) signed.
4) The bundle is sent to notarization with apple.
5) `.app` is stapled and compressed again for distribution.
6) Optional, if you have a `.dmg` installer, you rebuild it with the signed app and notarize it as well. 

`app-pass` helps you with steps 2 and 3.

For the process of acquiring the required signing certificate and app password, please see the [jaunch documentation](https://github.com/apposed/jaunch/blob/main/doc/MACOS.md#how-to-sign-your-applications-jaunch-launcher).

## Usage

<details><summary><b>If your bundle includes `.jar` files</b></summary>

These need to be extracted and can have case sensitive file contents.
Per default, the file system on the mac is _not_ case sensitive!
While many developers opt to change this when they get a new machine, not everyone does...
To mitigate this, we recommend creating a ram-disk for temporary files:

```bash
# creates a 2GB ramdisk at mountpoint /Volumes/ramdisk
# ram://2097152 for 1GB, ram://1048576 for .5GB
diskutil erasevolume hfsx 'ramdisk' `hdiutil attach -nomount ram://4194304`
```

You need to invoke all `app-pass` commands overriding then env variable `TMPDIR`, e.g. `TMPDIR=/Volumes/ramdisk app-pass fix ...`

</details>


### Check

```bash
# check if app would likely pass notarization and later gatekeeper
app-pass check <path_to_app_bundle.app>
```

### Fix

```bash
app-pass fix --sh-output debug.sh <path_to_app_bundle.app>
```

### Sign

```bash
app-pass fix --sh-output debug.sh <path_to_app_bundle.app> \
    <path/to/entitlements.plist> \
    <"Developer ID Application: <YOUR DEVELOPER APPLICATION INFO>">
```

### `--dry-run` and `--sh-output`

`app-pass` is built to make it easy for you to audit changes to your app.
Invoking `app-pass` with `--dry-run` and `--sh-output <output-script.sh>` will not do any changes to your app.
Instead, it will generate a shell script containing all the commands using standard Apple developer tools that would be executed to modify your app.


## Complete usage example

So far we've been working with the following `entitlements.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <key>com.apple.security.cs.allow-jit</key>
    <true/>
</dict>
</plist>
```

An example how we would sign our ilastik .app bundle:

```bash
# unzip unsigned app bundle after build
ditto -x -k ~/Downloads/ilastik-1.4.1rc3-arm64-OSX-unsigned.zip .
# this creates the bundle folder ilastik-1.4.1rc3-arm64-OSX.app that we will be
# working with

# fix and sign contents - for ilastik, we decide to remove rpaths that point
# outside the bundle so we add --rc-path-delete
app-pass fixsign \
    --sh-output "ilastik-1.4.1rc3-arm64-OSX-sign.sh" \
    --rc-path-delete \
    ilastik-1.4.1rc3-arm64-OSX.app \
    entitlements.plist \
    "Developer ID Application: <YOUR DEVELOPER APPLICATION INFO>"

# pack again to get ready for notarization
/usr/bin/ditto -v -c -k --keepParent \
    ilastik-1.4.1rc3-arm64-OSX.app ilastik-1.4.1rc3-arm64-OSX-tosign.zip

# send off to apple:
xcrun notarytool submit \
    --keychain-profile <your-keychain-profile> \
    --keychain <path-to-keychain> \
    --apple-id  <email-address-of-dev-account@provider.ext> \
    --team-id <your-team-id> \
    "ilastik-1.4.1rc3-arm64-OSX-tosign.zip"

# wait for notarization is complete
xcrun notarytool wait \
    --keychain-profile <your-keychain-profile> \
    --keychain <path-to-keychain> \
    --apple-id  <email-address-of-dev-account@provider.ext> \
    --team-id <your-team-id> \
    <notarization-request-id>

# once this is done, staple:
xcrun stapler staple ilastik-1.4.1rc3-arm64-OSX.app

# finally zip again for distribution
/usr/bin/ditto -v -c -k --keepParent \
    ilastik-1.4.1rc3-arm64-OSX.app ilastik-1.4.1rc3-arm64-OSX.zip
```

## Good reading material on the topic of signing/notarizing

* [Fun read on signing/notarization in general](https://blog.glyph.im/2023/03/py-mac-app-for-real.html), also the author of [encrust](https://github.com/glyph/Encrust)
* [Good overview of signing process, how to get certificates](https://briefcase.readthedocs.io/en/stable/how-to/code-signing/macOS.html) (briefcase documentation). Also probably a good option to develop your app from the start to ease with signing/notarizing.
* [Apple TN2206: macOS Code Signing In Depth](https://developer.apple.com/library/archive/technotes/tn2206/_index.html)
* [Apple docs on notarizing from the terminal](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow)


## What kind of issues does this package fix?

This package mostly manipulates the load commands of your Mach-O binaries using standard Apple developer tools such as `install_name_tool`, and `vtool`.
To look at any of these load commands `otool -l <dylib-path>` is your friend.

### Build versions and platform (`LC_BUILD_VERSION`)

Notarization requires `platform`, `minos`, and `sdk` versions to be set.
In older binaries these can be partly missing.

Another requirement is that `sdk` version is newer or equal to `10.9`.
There is the `--force-update` flag that will at least result in a app passing notarization.
We're still investigating if there's any downsides to this (for executables we found that they will not run, but libraries might work).

### Dynamic library search paths (`LC_RPATH`)

These paths may not point outside the `.app` folder for notarization to be successful (except for `/System/`, `/usr/`, `/Library/`).
`app-pass` tries do something sensible if these paths are absolute but point inside the app and replaces these with something relative to `@loader_path`, or `@executable_path`.

Some libraries have rpaths pointing outside the app.
Do these even exist on your machine?
The ones we found so far were artifacts of the build process and wouldn't exist on our machines.
The option `--rc-path-delete` will delete these rpaths from libraries.

### Linked dynamic libraries (`LC_LOAD_DYLIB`, `LC_REEXPORT_DYLIB`)

To pass notarization these paths may not be absolute, or point outside the app.
`app-pass` will try to locate the libs within the .app and add a relative link.

### Library ID (`LC_ID_DYLIB`)

This has to be a relative path inside the app.
Will be fixed to `@rpath/libname` if found otherwise.
