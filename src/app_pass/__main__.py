import typer

app = typer.Typer(name="app-pass", no_args_is_help=True)

@app.command()
def check():
    """Check if .app bundle is likely to pass MacOs Gatekeeper"""
    pass

@app.command()
def fix():
    """Fix issues in mach-o libraries .app bundle

    Remove paths that point outside the app.
    """
    pass

@app.command()
def sign():
    """Sign all binaries in the .app bundle"""
    pass

@app.command()
def notarize():
    """Zip app bundle using ditto and send off for notarization"""
    pass

@app.command()
def make_pass():
    """fix, sign, and notarize app"""
    pass


def main():
    app()

if __name__ == "__main__":
    main()
