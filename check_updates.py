#!/usr/bin/env python3
# Copyright (c) 2024 Jim Sloot (persei802@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import os
import requests

def check_for_updates():
    if not connection_available(): return
    print("Checking github for updated QtDragon")
    owner = "persei802"
    repo = "Qtdragon_hd"
    local_version = get_local_version()
    if local_version is None:
        print('No local version information found')
        return
    remote_version = get_remote_version(owner, repo)
    if remote_version is None:
        print("Remote request returned invalid response", WARNING)
        return
    if remote_version == local_version:
        print(f"This is the latest version ({local_version}) of Qtdragon_hd")
    else:
        print(f"There is a new version ({remote_version}) available")

def get_local_version():
    version = None
    fname = 'qtdragon/qtdragon_handler.py'
    if not os.path.exists(fname):
        print('QtDragon_handler.py not found')
        return version
    with open(fname, 'r') as handler:
        text = handler.read()
        lines = text.split('\n')
        for line in lines:
            if 'VERSION' in line:
                version = line.split('=')[1]
                version = version.strip(' ')
                version = version.strip("'")
                break
    return version

def get_remote_version(owner, repo):
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/qtdragon/qtdragon_handler.py"
    response = requests.get(url)
    version = None
    if response.status_code == 200:
        data = response.text
        lines = data.split('\n')
        for line in lines:
            if 'VERSION' in line:
                version = line.split('=')[1]
                version = version.strip(' ')
                version = version.strip("'")
                break
    return version

def connection_available(url="https://www.github.com", timeout=3):
    print('Checking internet connection')
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            return True
        else:
            print("Received response but not OK status")
            return False
    except requests.ConnectionError:
        print("No internet connection")
        return False
    except requests.Timeout:
        print("Connection timed out")
        return False

check_for_updates()
