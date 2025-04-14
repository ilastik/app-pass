# app-pass

Tool to ensure an `.app` bundle pass the Gatekeeper on MacOS.
Originally to sign the bundle for [ilastik](https://ilastik.org).

Prerequisite: You have built your app, and it runs on your own machine ;).
Problem: You try to sign/notarize but get back many errors and are unsure how to resolve them.

Tested so far with conda-based python apps, and java apps.

`app-pass` can perform various fixes on binaries, and sign `.app` bundles.
Does not require using a specific way to build your `.app` bundle.
Does not require `.app` being written in a specific language, or framework.

We understand that making changes to the binary that you are distributing should be as transparent as possible.
For this, you can generate an `.sh` file that uses only apple dev tools to manipulate your `.app`.
Any `app-pass` command invoked with `--dry-run` will not make any changes to your app.

## Installation

```
pip install git+https://github.com/k-dominik/app-pass.git
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

## Usage

<details><summary>**If your bundle includes `.jar` files**</summary>

These need to be extracted and can have case sensitive file contents.
Per default, the file system on the mac is _not_ case sensitive!
While many developers opt to change this when they get a new machine, not everyone does...
To mitigate this, we recommend creating a ram-disk for temporary files:

```bash
# creates a 2GB ramdisk at mountpoint /Volumes/ramdisk
# ram://2097152 for 1GB, ram://1048576 for .5GB
diskutil erasevolume hfsx 'RAM Disk' `hdiutil attach -nomount ram://4194304`
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


## Complete usage example

An example how we would sign our ilastik .app bundle:

```bash
# unzip unsigned app bundle after build
ditto -x -k ~/Downloads/ilastik-1.4.1rc3-arm64-OSX-unsigned.zip .
# this creates the bundle folder ilastik-1.4.1rc3-arm64-OSX.app that we will be working with

# fix and sign contents - for ilastik, we decide to remove rpaths that point outside the bundle
# so we add --rc-path-delete
app-pass fixsign \
   --sh-output "ilastik-1.4.1rc3-arm64-OSX-sign.sh" \
   --rc-path-delete \
   ilastik-1.4.1rc3-arm64-OSX.app \
   entitlements.plist \
   "Developer ID Application: <YOUR DEVELOPER APPLICATION INFO>"

# pack again to get ready for notarization
/usr/bin/ditto -v -c -k --keepParent ilastik-1.4.1rc3-arm64-OSX.app ilastik-1.4.1rc3-arm64-OSX-tosign.zip

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
/usr/bin/ditto -v -c -k --keepParent ilastik-1.4.1rc3-arm64-OSX.app ilastik-1.4.1rc3-arm64-OSX.zip
```

## Good reading material on the topic of signing/notarizing

* [Fun read on signing/notarization in general](https://blog.glyph.im/2023/03/py-mac-app-for-real.html), also the author of [encrust](https://github.com/glyph/Encrust)
* [Good overview of signing process, how to get certificates via briefcase](https://briefcase.readthedocs.io/en/stable/how-to/code-signing/macOS.html). Also probably a good option to develop your app from the start to ease with signing/notarizing.
* [Apple TN2206: macOS Code Signing In Depth](https://developer.apple.com/library/archive/technotes/tn2206/_index.html)
* [Apple docs on notarizing from the terminal](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow)
