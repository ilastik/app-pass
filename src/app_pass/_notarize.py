import json
import logging
import subprocess
import time
from pathlib import Path

LOGGER = logging.getLogger()


def compress(app_bundle: Path) -> Path:
    tosign_zip = app_bundle.parent / app_bundle.name.replace(".app", "-tosign.zip")
    LOGGER.info(f"Compressing {app_bundle} -> {tosign_zip}")
    subprocess.check_call(["/usr/bin/ditto", "-v", "-c", "-k", "--keepParent", str(app_bundle), str(tosign_zip)])
    return tosign_zip


def remove_apple_double(app_bundle: Path):
    LOGGER.info(f"Removing apple double in {app_bundle}.")
    subprocess.check_call(["find", str(app_bundle), "-type", "f", "-name", "._*", "-delete"])


def submit(tosign_zip: Path, keychain_profile: str, keychain: Path, apple_id: str, team_id: str) -> str:
    """
    {"path":"...","message":"...","id":"..."}
    """
    args = [
        "xcrun",
        "notarytool",
        "submit",
        "--output-format",
        "json",
        "--keychain-profile",
        keychain_profile,
        "--keychain",
        str(keychain),
        "--apple-id",
        apple_id,
        "--team-id",
        team_id,
        str(tosign_zip),
    ]
    LOGGER.info(f"Submitting {tosign_zip}")
    output = json.loads(subprocess.check_output(args))
    LOGGER.info(f"{tosign_zip} submitted successfully with submission id: {output['id']}")
    return output["id"]


def check(submission_id: str, keychain_profile: str, keychain: Path, apple_id: str, team_id: str) -> str:
    """
    {"status":"Accepted","message":"Successfully received submission info","name":"ilastik-1.4.1rc2-arm64-OSX-tosign.zip","id":"cdd139bf-5f03-412e-9f26-dc640f19bd17","createdDate":"2025-02-27T07:25:01.041Z"}

    """
    args = [
        "xcrun",
        "notarytool",
        "info",
        "--output-format",
        "json",
        "--keychain-profile",
        keychain_profile,
        "--keychain",
        str(keychain),
        "--apple-id",
        apple_id,
        "--team-id",
        team_id,
        submission_id,
    ]
    output = json.loads(subprocess.check_output(args))
    LOGGER.info(f"{output['name']} submission id: {output['id']} - status: {output['status']}")
    return output["status"].lower()


def staple(app_bundle: Path):
    args = ["xcrun", "stapler", "staple", str(app_bundle)]
    LOGGER.info(f"Stapling {app_bundle}")
    output = subprocess.check_output(args)
    LOGGER.info(output)


def notarize_impl(app_path: Path, keychain_profile: str, keychain: Path, apple_id_email: str, team_id: str) -> int:
    """Notarize an .app bundle with given credentials, wait for completion and staple

    This is equivalent to doing the following steps manually:

    # pack to get ready for notarization
    /usr/bin/ditto -v -c -k --keepParent \
        myapp.app myapp-tosign.zip

    # send off to apple:
    xcrun notarytool submit \
        --keychain-profile <your-keychain-profile> \
        --keychain <path-to-keychain> \
        --apple-id  <email-address-of-dev-account@provider.ext> \
        --team-id <your-team-id> \
        "myapp-tosign.zip"

    # wait for notarization is complete
    xcrun notarytool wait \
        --keychain-profile <your-keychain-profile> \
        --keychain <path-to-keychain> \
        --apple-id  <email-address-of-dev-account@provider.ext> \
        --team-id <your-team-id> \
        <notarization-request-id>

    # once this is done, staple:
    xcrun stapler staple myapp.app

    """
    remove_apple_double(app_path)
    tosign_zip = compress(app_path)
    submission_id = submit(tosign_zip, keychain_profile, keychain, apple_id_email, team_id)

    OVERALL_TIMEOUT = 40 * 60
    SLEEP_S = 60
    timeout = time.perf_counter() + OVERALL_TIMEOUT

    status = "NEVER CHECKED"
    while timeout > time.perf_counter():

        status = check(submission_id, keychain_profile, keychain, apple_id_email, team_id)
        LOGGER.info(f"Submission status {status} for {submission_id}")
        if status == "accepted":
            break
        time.sleep(SLEEP_S)

    LOGGER.info(f"Notarization finished with {status=}")
    if status == "accepted":
        staple(app_path)

    if status == "accepted":
        return 0
    else:
        return -1
