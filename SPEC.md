# StopActionPi specification

StopActionPi is a small stop motion studio for a Raspberry Pi 500 and a USB webcam. A child can move a figure, capture a frame with the built-in keyboard, and watch the scene come to life. The app keeps the photos so a movie can be finished or exported later.

## App behavior

| What a maker needs | Behavior |
| --- | --- |
| Open the studio | The desktop icon opens directly. The app is also in the application menu and opens automatically at desktop login. |
| Start or resume a movie | The welcome screen highlights Continue Selected Movie when there are recent movies, or New Movie on a fresh setup. Open Movie Folder finds projects elsewhere. The studio opens fullscreen after a project is chosen. F11 switches to window view. |
| See the scene | Show the live camera, photo count, and buttons with visible shortcuts in one window. Request 1280 × 720 from the Logitech C270. |
| Take a photo | Space saves one clean PNG and updates the thumbnail strip. Holding Space does not add extra photos. |
| Remember what moved | O overlays the newest photo on the live image. The arrow keys let the maker flip between saved photos. |
| See the motion | P plays from the first photo to the latest. L loops the last six at up to six photos per second. Space pauses or resumes review. Esc returns to the camera. |
| Change the speed | S switches between 6 and 12 fps for full playback and the next MP4 export. Show the selected speed and estimated movie length. |
| Fix a shot | R arms a retake of the last photo. Space saves the replacement to the same slot. Esc cancels and keeps the original. |
| Remove a shot | During review, Delete asks to remove the selected photo. Enter removes it from the project sequence and Esc keeps it. The original remains in the local `.removed` folder. |
| Fade between shots | F sets the duration of a crossfade into the next photo. A fade adds blended frames to playback and export while preserving the source photos. Enter zero to remove it. |
| Make a movie | E writes a silent H.264 MP4 at the selected rate. Playback and export default to 6 photos per second. Exports get distinct filenames. |
| Join finished movies | J opens a list where makers pick and order two or more MP4s from any project. Join writes a new silent MP4 in the current project. The original clips keep their timing and remain on disk. |
| Join photo folders | I opens a list of folders. Join copies supported images in folder order and sorts each folder's files by name with numbers in sequence. The new folder starts at 000 and can be opened as a project for review and export. |
| Narrate a movie | N opens the Recording Studio. Makers scrub a finished MP4, mark a section, and rehearse with a lead-in. R starts a countdown and records the selected section. P previews the pending take, K keeps it, and E saves a new MP4. The rest of the narration stays in place. |
| Continue tomorrow | Reopen the same project folder and capture continues after the last saved photo. |

## Implementation

- The target is Raspberry Pi OS Desktop on a Pi 500. Capture and review share one primary window on a single monitor. The join and narration tools open separate panels on that monitor.
- Camera, review, retake, and removal confirmation have their own button sets. A button and its key call the same action. Movie Tools keeps joins and narration together.
- The camera preview pauses updates during resizing. Once the window settles, the app redraws the photo and all visible buttons.
- OpenCV reads frames in the background so a slow webcam does not hold up review. Tk draws the preview and keyboard controls. FFmpeg writes H.264 MP4 files with AAC audio for narrated exports.
- Camera projects save numbered PNGs. Joined photo folders preserve the source formats and use names starting at `000`. Deleting a photo moves it into `.removed/`, and playback and exports use the remaining photos in numeric order.
- Fades are saved in the project's `.transitions.json` with the two photo filenames and the duration in seconds. Playback and export use a fade only while those photos are adjacent. Export streams the blended frames to FFmpeg.
- The Recording Studio loads existing narration or starts with a silent track. Retakes are temporary until kept. A kept take replaces only the recorded part of its marked section. Saving writes a new MP4 with the edited audio and copies the original video stream.
- Project folders remain local. The installed studio works without an account or internet connection.

## Source guide

| File | Role |
| --- | --- |
| [`stop_motion.py`](stop_motion.py) | Webcam capture, frame storage, review, and MP4 export |
| [`project_picker.py`](project_picker.py) | Welcome screen and project selection |
| [`install_desktop.py`](install_desktop.py) | Per-user desktop icon, menu entry, and autostart |
| [`transitions.py`](transitions.py) | Saved fade settings and blending between adjacent photos |
| [`ui_controls.py`](ui_controls.py) | Clickable buttons with key badges and responsive button rows |
| [`clip_joiner.py`](clip_joiner.py) | Ordered joins for MP4 clips and photo folders |
| [`narration_studio.py`](narration_studio.py) | Narration timeline, recording controls, cue line, and take review |
| [`narration.py`](narration.py) | Microphone selection, audio editing, playback preparation, and narrated MP4 export |

## First run acceptance check

1. Double-click the desktop icon. Confirm that the welcome screen opens directly. Choose a movie and verify that the C270 preview opens fullscreen. Use Window View or F11 to switch back and confirm that the buttons remain visible.
2. Capture three distinct photos. Verify the thumbnail strip grows and the saved PNGs contain only the camera image.
3. Move a prop and use O to compare positions. Use the arrows to flip between the last two saved photos.
4. Play all three photos at both speeds and loop them. Add a one-second fade after the first photo and check that playback and export gain one second. Return to live capture.
5. Cancel a retake, then complete one. Check that the photo count stays at three and that only the last shot changes.
6. Remove the middle photo in review. Play and export the remaining two in order. Quit and reopen the project, then capture a new photo. The new shot should follow the two remaining photos.
7. Join two exports at different speeds. Check that they appear in the chosen order and keep their original pacing. Join two photo folders and verify that numbering continues across the folder boundary.
8. Open an exported MP4 in the Recording Studio, mark a short section, and rehearse. Record it, listen back, and keep the take. Save and reopen the narrated MP4. Replace a second section and check that the first take is still in place.
