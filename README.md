# app-pass

Tool to ensure an `.app` bundle pass the Gatekeeper on MacOS.

Can perform various fixes on binaries, sign and notarize `.app` bundles.

## Installation

```
# TODO
```

## Usage

### Check

```bash
# check if app would likely pass notarization and later gatekeeper
app-pass check <path_to_app_bundle.app>
```

### Fix


```bash
app-pass fix <path_to_app_bundle.app>
```

### Sign

...

### Notarize

...

## Design

### 1. Language Agnostic

We don't have an opinion on how you arrive at your `.app` bundle.
We also don't want to force any framework, or programming language on you.
`app-pass` should work with all kinds of `.app` bundles and should make getting them notarized a more straight forward process.

### 2. Auditable

We understand modifying your `.app` bundle that you want to distribute is a sensitive matter.
`app-pass` makes it easy to interrogate what will be changed in your `.app` when using the `--dry-run` option and specifying a shell-script to write to with `--sh-cmd-out <myfile.sh>`.
The generated shell script can 1) be executed without `app-pass`, and can be inspected prior to its execution.

### 3. Rely on MacOs standard tools

There are great libraries around (e.g. [macholib](https://github.com/ronaldoussoren/macholib)) to inspect and modify mach-o files.
The surface touched by `app-pass` is rather small, so that it is doable relying only on standard developer tools on MacOs.
Additionally, this allows generating scripts that can be run outside of `app-pass` and in general allows developers to follow more easily what is changing how, if they're already familiar with those tools.
