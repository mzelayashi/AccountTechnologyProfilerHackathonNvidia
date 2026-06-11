#!/usr/bin/env bash
# Opens ATLAS in a terminal window (used by the "Start ATLAS" shortcut / menu entry).
cd "$(dirname "$(readlink -f "$0")")"

if command -v xfce4-terminal >/dev/null 2>&1; then
    exec xfce4-terminal --working-directory="$PWD" --title="SHI ATLAS" --command="./launch_atlas.sh"
elif command -v gnome-terminal >/dev/null 2>&1; then
    exec gnome-terminal --working-directory="$PWD" --title="SHI ATLAS" -- bash -c './launch_atlas.sh'
else
    exec x-terminal-emulator -e bash -c "cd '$PWD'; ./launch_atlas.sh"
fi
