# app-pass Development

## Create a development environment

```bash
conda env create --file dev/environment-dev.yaml
```

This will create an environment with the name `app_pass`, that can be activated with `conda activate app_pass`.

## Automatic versioning with bumpversion

The following versioning scheme is implemented `<major>.<minor>.<patch><release-type><build>`. `major`, `minor`, and `patch` shouldn't need more introduction.
The only _special_ thing here is the `release-type` with its `build`. `release-type` will take the value of `dev` as a default and the `build` is a simple counter.

```
1.2.3dev4
^ ^ ^ ^ ^     command                 result
| | | | |
| | | | +--+ `bumpversion build`   -> 1.2.3dev5
| | | |
| | | +----+ `bumpversion release` -> 1.2.3
| | |
| | +------+ `bumpversion patch`   -> 1.2.4dev0
| |
| +--------+ `bumpversion minor`   -> 1.3.0dev0
|
+----------+ `bumpversion major`   -> 2.0.0dev0

```

## Dependency management

There are two different types of dependencies:

1) Package dependencies for deployment: These dependencies should be added to your project's `setup.py` under the requirements section. These packages are automatically added to the conda recipe in `conda-recipe/meta.yaml`. 
2) Development dependencies: All packages that are needed for development, should be added to your package's `dev/environment-dev.yaml`.

## Black style checking / pre-commit

This repo comes with a `.pre-commit-config.yaml` that allows for convenient automatic use of the [black](https://github.com/ambv/black) code formatter.
Black will be run before every commit. In case reformatting is necessary, the commit action is aborted. Reformatted changes have to be added and the commit has to be triggered again.
