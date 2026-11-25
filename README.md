# StopActionPi

Make a stop motion movie on a Raspberry Pi. Move a figure a little, take a photo, and play your movie as it grows. The live camera, recent photos, and keyboard guide fit on one screen. StopActionPi runs locally and keeps each movie's source photos and exports in its project folder.

## What you need

- A Raspberry Pi 500 running 64-bit Raspberry Pi OS Desktop. The app was tested on the Debian 13 (Trixie) release.
- A monitor and USB webcam. The Logitech C270 was tested at 1280 × 720. A fixed camera and steady light help keep shots consistent.
- For narration, a microphone and an audio output you can listen to. The C270 has a built-in mic, and a monitor with HDMI speakers can play the preview.

## Install on the Pi

Connect the webcam to USB. From a terminal on the Pi desktop, run:

```bash
sudo apt update
sudo apt install git python3-opencv python3-tk ffmpeg v4l-utils libglib2.0-bin
git clone https://github.com/luminerdy/StopActionPi.git
cd StopActionPi
python3 install_desktop.py
```

Double-click the **StopActionPi** desktop icon or choose it from the application menu. The app also opens when your desktop session starts. On a Pi with Desktop Auto Login enabled, this happens at boot. The launcher uses a project `.venv` if present, or the system Python with the packages above.

On the welcome screen, pick a recent movie and choose **Continue Selected Movie**. Choose **New Movie** to start another one or **Open Movie Folder** to find a project elsewhere on the Pi. New movies go under `projects/` in the app folder. The studio goes fullscreen after you pick a folder. Choose **Window View** or press **F11** to switch between full screen and a window. To try the app without creating launchers, run `python3 stop_motion.py` from a terminal on the Pi desktop.

To update an installation made with Git, quit StopActionPi, open a terminal in the app folder, and run:

```bash
git pull --ff-only
python3 install_desktop.py
```

Running the installer again refreshes the desktop shortcut, menu entry, and autostart entry.

## Make a movie

Fix the camera in place and light the scene. Click **Take Photo** or press **Space** for the first photo. Move your subject a little and take another one. Once you have three photos, choose **Play Movie** or press **P** to watch them move, then choose **Save Movie** or press **E** to save an MP4. The buttons change as you move between the camera, photo review, and retake screens. Each shows the key that does the same thing.

| Key | What it does |
| --- | --- |
| **Space** | Take and save a photo in the live view. Pause or play in review. |
| **O** | Show or hide a faint copy of the last photo so you can see what moved. |
| **← / →** | Open the latest saved photo, then step through the photos one by one. |
| **Delete** | Remove the photo shown in review. Press **Enter** to remove it or **Esc** to keep it. |
| **F** | Add or edit a fade from the selected photo into the next one. |
| **P** | Play the movie from the first photo through the newest one. |
| **L** | Replay the last six photos slowly to check the motion. |
| **S** | Switch between 6 fps and 12 fps for full playback and the next MP4 export. The current speed is displayed at the top. |
| **Esc** | Return to the live camera or cancel a retake. |
| **R** | Set up a retake. **Space** replaces the last photo and **Esc** keeps it. |
| **E** | Save Movie creates an MP4 in the project folder. Wait for “Movie saved!” on screen. |
| **M** | Show or hide Movie Tools for joining movies, joining photo folders, or adding your voice. |
| **J** | Join two or more saved MP4s into one movie. |
| **I** | Copy photos from one or more folders into a new numbered sequence. |
| **N** | Record narration for a finished MP4 using a connected microphone. |
| **F11** | Switch between full screen and window view. |
| **Q** | Quit. Your photos are already saved. |

With straight cuts, 60 photos make a 5-second movie at 12 fps or a 10-second movie at 6 fps. **Space** saves one photo at either speed. Try small, consistent movements and keep your hands out of the scene when you press Space.

## Fade between photos

In review, use the arrow keys to pick the photo where the fade should begin. Press **F** and enter the number of seconds. The fade blends that photo into the next one and adds that time to the movie, rounded to the nearest frame. Press **Space** to preview from the selected photo, **P** to play the full movie, or **E** to export it with the fade.

Fades are saved with the project. Press **F** again to change a fade, or enter `0` to remove it. Your original photos stay intact. Removing either photo skips the fade.

## Join finished movies

Press **J**, then **A** to add each MP4 you want to use. Clips can come from different project folders. They play from the top of the list down. Use the arrow keys to select a clip, **U** or **D** to move it, and **Delete** to take it out of the list. The clips on disk stay as they are.

Press **Enter** to save a new `joined_*.mp4` in the current project folder. A clip exported at 6 fps stays slow beside one exported at 12 fps. The joined movie is silent, like the studio's individual exports.

## Join photo folders

Press **I**, then **A** for each image folder you want to add. The studio reads each folder from top to bottom in the order shown. Within a folder, filenames sort by number, so `photo2.png` goes before `photo10.png`. Use **U** or **D** to move a selected folder.

Press **Enter** to create a new `joined_images_*` folder inside your current project. Photos are copied with their original formats, starting at `000` and counting up across all the selected folders. The join includes PNG, JPEG, BMP, TIFF, and WebP photos directly inside each folder.

To review the joined sequence or turn it into an MP4, reopen StopActionPi and choose **Open Movie Folder**. Select the new `joined_images_*` folder inside the original project.

## Recording Studio

Finish and export your movie. If you're making it from several MP4s, join them before recording. Open **Movie Tools** and choose **Add My Voice**, or press **N**. Choose your movie with **A**. You can start with a silent movie or reopen one with narration already on it.

1. Use the arrow keys or click the timeline to find the start. Press **1** to mark it. Find the end and press **2**. Leave the marks as they are to record the whole movie. Type an optional cue line in the text box.
2. Press **T** to rehearse with up to three seconds of lead-in. Press **R** to record the section after a countdown. Speak when you see “Recording.” The take stops at the end of the section, or press **S** to stop early.
3. Press **P** to listen back. **K** keeps the new take, **R** tries again, and **X** discards the pending take. The rest of the narration stays in place. If you stopped early, only the part you recorded is replaced.
4. Press **E** after keeping a take to save a new `narrated_*.mp4` in the current project. Reopen that MP4 to continue editing later. The original movie stays intact.

The app prefers the Logitech C270 microphone when it finds one in the Pi desktop's audio sources.

## Resume or change playback speed

Quit with **Q** and open StopActionPi again. Choose the same movie on the welcome screen to reload your photos. The app starts at 6 fps, and **S** switches between 6 and 12 fps during a session. For terminal use from the Pi desktop, `--project` skips the welcome screen and `--fps` picks the starting speed. Open each project in one window at a time.

```bash
python3 stop_motion.py --project projects/first_movie --fps 8
python3 stop_motion.py --project projects/first_movie --fps 12 --export-only
```

Export-only works without a webcam or preview. Each export gets a new filename. Removed photos are skipped in playback and new exports. To recover one, quit the app, move its numbered image from the hidden `.removed` folder back into the project folder, and reopen the project. Frame exports are silent. Use the Recording Studio to make a copy with audio.

## Camera troubleshooting

Close other programs using the camera. List devices with:

```bash
v4l2-ctl --list-devices
```

If necessary, start from a desktop terminal with `python3 stop_motion.py --camera 1` or another device number. The program requests 1280 by 720. The webcam driver chooses the actual resolution. Camera projects use a consistent capture size. Joined photo folders can contain mixed dimensions, which the app fits to the first photo's size on export.

For flicker, use steady lighting and avoid changing daylight. Inspect available exposure and white-balance controls with `v4l2-ctl -d /dev/video0 --list-ctrls-menus`. Supported controls vary; locking exposure and white balance can improve consistency.

## Project details

See the [project specification and first run checks](SPEC.md) for behavior, file formats, and a guide to the source. See [LICENSE](LICENSE) for reuse terms.

See also [Logitech C270 specifications](https://support.logi.com/hc/en-001/articles/360023393913-Logitech-HD-Webcam-C270-Technical-Specifications) and [Raspberry Pi USB webcam documentation](https://www.raspberrypi.com/documentation/accessories/camera-software.html).
