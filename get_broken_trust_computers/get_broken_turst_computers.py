"""Get Broken Trust Computers

This script is designed to create a static group of computers in JAMF that have
completed MDM commands more recently than they have checked in, implying a
broken JAMF agent trust which you can later action (e.g. using the self healing
feature introduced in JAMF Pro 10.36).

This script requires Python 3.

You will need to pre-create the static group and advanced search the script
queries to get a list of computers to process. (e.g. computer is managed and
last checkin more than 20 days ago) and then provide their ID numnbers at the
start of the script.

You will need to either provide the JAMF URL, API username, and API password via
environmental variables or fall back to hardcoding it into the script after the
"or" statement.

This script requires JAMF 10.35 or above because of using the newer token method
for authentication.

This script requires the aiohttp module to be installed via pip for doing
asyncio https requests.
    - Since async network requests can potentially make requests significantly
      faster than synchronous network requests you could possibly hit api call
      limits that I am unaware of in JAMF's hosted cloud environment.
    - If your server or database server is underspecced you could see noticeably
      slower response of your JAMF server while the script is pulling data.

"""

import aiohttp
import asyncio
import os
import time
import json
from datetime import datetime, timedelta

JAMF_API_URL = os.getenv("JAMF_API_URL") or "" # https://myjamfserver.company.com
JAMF_API_USER = os.getenv("JAMF_API_USER") or "" 
JAMF_API_PASS = os.getenv("JAMF_API_PASS") or ""
MANAGED_MACS_ADVANCED_SEARCH_ID = # ID number of advanced search
BROKEN_TRUST_STATIC_GROUP = # ID number of static group to push results to
MAX_DAYS_SINCE_LAST_COMPLETED_MANAGEMENT_COMMAND = 15

# Enable or disable SSL verification for JAMF if you are having issues
SSL_VERIFICATION = True

NOW = datetime.now()

COUNTER = 0
COMPUTER_COUNT = 0


async def get_auth_token():
    """Get auth_token from JAMF API (10.35 and above)"""
    async with aiohttp.ClientSession(
        headers={
            "accept": "application/json",
        },
        connector=aiohttp.TCPConnector(ssl=SSL_VERIFICATION),
        auth=aiohttp.BasicAuth(
            login=JAMF_API_USER, password=JAMF_API_PASS, encoding="utf-8"
        ),
    ) as aiohttp_session:
        response = await aiohttp_session.post(url=f"{JAMF_API_URL}/api/v1/auth/token")
        return json.loads(await response.text())["token"]


async def get_all_managed_macs(aiohttp_session):
    """Get managed Mac IDs from an advanced search set up with desired last checkin time"""
    r = await aiohttp_session.get(
        f"{JAMF_API_URL}/JSSResource/advancedcomputersearches/id/{MANAGED_MACS_ADVANCED_SEARCH_ID}",
    )
    raw_json = await r.text()
    computers = json.loads(raw_json)
    return [
        {"name": computer["name"], "id": computer["id"]}
        for computer in computers["advanced_computer_search"]["computers"]
    ]


async def process_managed_command_history(aiohttp_session, computers):
    """Processes computers managed command history and return those that meet our criteria for broken trust"""
    # Set the global COMPUTER_COUNT variable to the total number of computers so
    # we have a number to compare to when printing out progress
    global COMPUTER_COUNT
    COMPUTER_COUNT = len(computers)
    # Use a generator expression to create an asyncio queue of individual
    # calls for each computer to the get_managed_command_history function
    computers_and_mdm_commands = await asyncio.gather(
        *(
            get_managed_command_history(aiohttp_session, computer)
            for computer in computers
        )
    )

    final_computers = []
    # Create a datetime object for the current time - our desired amount of days
    # to get a time range to filter against
    time_limit = NOW - timedelta(days=MAX_DAYS_SINCE_LAST_COMPLETED_MANAGEMENT_COMMAND)
    for computer in computers_and_mdm_commands:
        if computer["commands"]:
            # Return the completed mdm command with the most recent timestamp
            newest_time_epoch = max(
                computer["commands"], key=lambda x: x["completed_epoch"]
            )
            # Create a datetime object for comparison use
            newest_time = datetime.fromtimestamp(
                newest_time_epoch["completed_epoch"]
                / 1000  # JAMF provides epoch time in milliseconds while datetime uses seconds so we must divide by 1000 to get useable time
            )
            if newest_time > time_limit:
                final_computers.append((computer["id"]))
    return final_computers


async def get_managed_command_history(aiohttp_session, computer):
    "Get and return history of completed MDM commands from the API for an individual computer"
    r = await aiohttp_session.get(
        f"{JAMF_API_URL}/JSSResource/computerhistory/id/{computer['id']}"
    )
    # Increment global counter so that when printing what computer we are processing we have a basic idea of total progress
    global COUNTER
    COUNTER += 1
    print(
        f"Getting managed commands history for {computer['name']}   {COUNTER}/{COMPUTER_COUNT}"
    )
    raw_json = await r.text()
    j = json.loads(raw_json)
    return {
        "id": computer["id"],
        "commands": j["computer_history"]["commands"]["completed"],
    }


def build_group_xml(computer_ids):
    """Build xml of computer IDs we intend to submit to the API for static group membership"""
    computer_xml = "".join(
        [f"<computer><id>{computer_id}</id></computer>" for computer_id in computer_ids]
    )
    return f"<computer_group><computers>{computer_xml}</computers></computer_group>"


async def submit_static_group(aiohttp_session, xml):
    """Submit xml payload of computer IDs to refresh static group membership"""
    r = await aiohttp_session.request(
        method="PUT",
        url=f"{JAMF_API_URL}/JSSResource/computergroups/id/{BROKEN_TRUST_STATIC_GROUP}",
        data=xml,
    )
    print(r.status)


async def main():
    auth_token = await get_auth_token()
    async with aiohttp.ClientSession(
        headers={
            "accept": "application/json",
            "Authorization": f"Bearer {auth_token}",
        },
        connector=aiohttp.TCPConnector(ssl=SSL_VERIFICATION),
    ) as aiohttp_session:
        computers = await get_all_managed_macs(aiohttp_session)
        mdm_alive_computers = await process_managed_command_history(
            aiohttp_session, computers
        )
        xml_to_post = build_group_xml(mdm_alive_computers)
        await submit_static_group(aiohttp_session, xml_to_post)


if __name__ == "__main__":
    # Create perf counter to figure out how long script takes to run (for testing)
    s = time.perf_counter()
    asyncio.run(main())
    elapsed = time.perf_counter() - s
    print(f"{__file__} executed in {elapsed:0.2f} seconds.")
