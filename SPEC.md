# StopActionPi specification

StopActionPi is a small stop motion studio for a Raspberry Pi 500 and a USB webcam. A child can move a figure, capture a frame with the built-in keyboard, and watch the scene come to life. The app keeps the photos so a movie can be finished or exported later.

## App behavior

| What a maker needs | Behavior |
| --- | --- |
| Open the studio | The desktop icon opens directly. The app is also in the application menu and opens automatically at desktop login. |
| Start or resume a movie | The welcome screen highlights Continue Selected Movie when there are recent movies, or New Movie on a fresh setup. Open Movie Folder finds projects elsewhere. My Movies opens the picker from inside the studio. The studio opens fullscreen after a project is chosen. F11 switches to window view. |
| See the scene | Show the live camera, photo count, and buttons with visible shortcuts in one window. Request 1280 × 720 from the Logitech C270. |
| Take a photo | Space saves one clean PNG and updates the thumbnail strip. Holding Space does not add extra photos. |
| Remember what moved | O overlays the newest photo on the live image. Review has clickable and scrollable thumbnails, arrow-key stepping, and Home and End jumps. Thumbnails identify messages, drawings, and fades. |
| See the motion | P plays from the first photo to the latest. L loops the last six at up to six photos per second. Space pauses or resumes review. Esc returns to the camera. |
| Change the speed | S opens a slider for choosing a whole-number speed from 2 to 32 fps for full playback and the next MP4 export. Show the selected speed and estimated movie length. |
| Fix a shot | R arms a retake of the last photo. Space saves the replacement to the same slot. Esc cancels and keeps the original. |
| Hold a shot | During review, D asks for 1 to 1,000 extra copies of the selected photo. Insert the copies right after the selected photo. An outgoing fade moves after the last copy. |
| Reorder shots | During review, Move Earlier and Move Later (Shift+Left and Shift+Right) move the selected photo one position at a time. Keep that photo selected and save the new order immediately. |
| Put words on a photo | T opens a live preview with editable text, top or bottom placement, paired styles, two color palettes, and a hold time from 1 to 30 seconds. The default is a 3-second hold. Reopen the editor to change or remove the message. |
| Draw on a photo | B opens a mouse or touchpad drawing surface with the message color palette and three brush sizes. Use Undo or Ctrl+Z to take back a stroke. Clear Drawing with Save Drawing removes the drawing. |
| Remove a shot | During review, Delete asks to remove the selected photo. Enter archives it and Esc keeps it. Undo Remove or Ctrl+Z restores the most recently removed photo, its position, and its saved edits before a subsequent change to the photo sequence. |
| Fade between shots | F sets the duration of a crossfade into the next photo. A fade adds blended frames to playback and export while preserving the source photos. Enter zero to remove it. |
| Make a movie | Finish groups export, narration, and joins. E writes a silent H.264 MP4 at the selected rate. After a successful save, Finish can open the movie or its folder. Playback and export default to 6 photos per second. |
| Join finished movies | J opens a list where makers pick and order two or more MP4s from any project. Join writes a new silent MP4 in the current project. The original clips keep their timing and remain on disk. |
| Join photo folders | I opens a list of folders. Join copies supported images using each folder's saved photo order when available and numeric filename order otherwise. The new folder starts at 000 and can be opened as a project for review and export. |
| Narrate a movie | N opens the current cut in Recording Studio, with an option to choose an existing MP4. Makers scrub the movie, mark a section, and rehearse with a lead-in. R starts a countdown and records the selected section. P previews the pending take, K keeps it, and E saves a new MP4. The rest of the narration stays in place. |
| Continue tomorrow | Reopen the same project folder and capture continues after the last saved photo. |

## Implementation

- The target is Raspberry Pi OS Desktop on a Pi 500. Capture and review share one primary window on a single monitor. The join and narration tools open separate panels on that monitor.
- Camera and Review show their main controls first. Camera Tools and Edit Photo open secondary controls. Finish groups MP4 export, joins, and narration. A button and its key call the same action.
- The camera preview pauses updates during resizing. Once the window settles, the app redraws the photo and all visible buttons.
- OpenCV reads frames in the background so a slow webcam does not hold up review. Tk draws the preview and keyboard controls. FFmpeg writes H.264 MP4 files with AAC audio for narrated exports.
- Camera projects save numbered PNGs. Joined photo folders preserve the source formats and use names starting at `000`. Deleting a photo moves it into `.removed/`. Duplicating a photo creates independent image files. Duplicating and reordering save the photo sequence in the project's `.frame-order.json`. Review, playback, export, and photo-folder joins use the saved sequence or fall back to filename order.
- Fades are saved in the project's `.transitions.json` with the two photo filenames and the duration in seconds. Playback and export use a fade only while those photos are adjacent. Export streams the blended frames to FFmpeg.
- Messages are saved in `.photo-messages.json` by photo filename. Pillow draws messages in review, preview, and MP4. The message is shown throughout its photo's hold. Fades blend the adjacent photos after the hold.
- Drawings are saved in `.photo-drawings.json` as strokes with positions relative to each photo. Review, playback, and export render the drawings beneath any messages. Drawings crossfade with their photos.
- The Recording Studio loads existing narration or starts with a silent track. Retakes are temporary until kept. A kept take replaces only the recorded part of its marked section. Saving writes a new MP4 with the edited audio and copies the original video stream.
- Camera exports, joined movies, and narrated movies use the project folder name, local date and time, and an export label in the filename. When a filename is taken, saving adds the next available number.
- Project folders remain local. The installed studio works without an account or internet connection.

## Source guide

| File | Role |
| --- | --- |
| [`stop_motion.py`](stop_motion.py) | Webcam capture, frame storage, review, and MP4 export |
| [`movie_output.py`](movie_output.py) | Project-based MP4 names and collision handling |
| [`photo_sequence.py`](photo_sequence.py) | Photo duplication, reordering, and saved sequence order |
| [`photo_messages.py`](photo_messages.py) | Message storage, rendering, and timing |
| [`message_dialog.py`](message_dialog.py) | Message editor, color swatches, and preview |
| [`photo_drawings.py`](photo_drawings.py) | Saved strokes and drawing rendering |
| [`drawing_dialog.py`](drawing_dialog.py) | Freehand drawing, brush controls, and undo |
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
9. In review, select a photo and use D to add three copies. Reopen the project and verify the copies still follow the selected photo. Remove one copy and confirm the other copies and original are still in the movie.
10. Move a photo earlier with the button, then later with Shift+Right. Verify each move keeps the photo selected. Reopen the project and export an MP4 to check the saved order.
11. Add a message with T. Pick a style, change a color and the hold time, and export. Reopen the project, verify the settings, and remove the message in the editor.
12. Open B, draw two strokes in different colors and sizes, undo one, and save. Verify the drawing after reopening and in the MP4. Clear the drawing and save again.

<a id="camera-review-and-finish-implementation-plan"></a>

## Camera, Review, and Finish

StopActionPi uses one window on one monitor. Camera keeps the capture controls within reach. Review keeps the picture large and opens editing tools as needed. Finish is available from both views.

| Where | On screen | Open as needed |
| --- | --- | --- |
| **Camera** | Large **Take Photo [Space]**, **Show Last Photo [O]**, **Replay Last 6 [L]**, **Review Photos**, and **Play Movie [P]**. | **Camera Tools [C]** opens **Retake Last [R]**. |
| **Review** | Large photo, clickable thumbnail strip, **Back to Camera [Esc]**, **Previous**, **Next**, and **Play From Here [Space]**. | **Edit Photo [Enter]** groups **Move Earlier/Later**, **Duplicate Photo [D]**, **Remove Photo [Delete]**, **Message [T]**, **Draw [B]**, and **Fade to Next Photo [F]**. |
| **Finish** | **Save MP4 [E]**, **Add My Voice [N]**, **Join Movies [J]**, and **Join Photo Folders [I]**. After a save, show the filename and offer **Watch Saved Movie** and **Show in Folder**. | A **Choose Existing MP4** path inside Recording Studio supports editing an earlier export. |

The header shows the project name, photo count, estimated duration, and **Speed [S]** in both Camera and Review. It also holds **My Movies [Ctrl+O]**, the fullscreen toggle, and **Quit [Q]**. **Finish [M]** opens the finishing controls and **Esc** returns to the previous view. Direct keyboard shortcuts work with the tools panels closed.

- **Review.** Click thumbnails or scroll the strip. **Home** and **End** jump to the first and last photo. **T**, **B**, and **F** on a thumbnail mark a message, drawing, or outgoing fade. **Undo Remove [Ctrl+Z]** restores the latest removal in the current session until the next change to the photo sequence.
- **Finish.** The saved-file actions appear after a successful MP4 save. **Add My Voice** opens the current cut in Recording Studio and creates a new export if the cut or speed changed. **Choose Existing MP4** can open an earlier export.
- **My Movies.** The picker can open another project while the app stays open. The studio releases the previous project's camera and playback resources when switching. Recording Studio asks before discarding unsaved takes, and active saves must finish before switching.

The layout was checked at 1280 × 720 and 1920 × 1080. At 1280 × 720, the default Review view went from 17 visible buttons to 10 and gained about 100 pixels of preview height.

## Future work

- **Steadier shots.** Check what focus, exposure, and white-balance controls each webcam exposes. Add a focus lock first, then a preview grid and adjustable strength for Show Last Photo.
- **Easier timing.** Add **Hold This Photo** for a drawing or dramatic pause. Remember each project's chosen speed and start new projects at 6 fps. Add **Retake This Photo** for a shot in the middle of a sequence.
- **Editable scene joins.** When joining photo folders, carry over the photo-linked messages and drawings, and remap fades to the renamed neighbor photos. For MP4 joins, preserve audio and the timing of 32 fps clips.
- **Hide a support.** Save a clean photo of the set and use a brush to reveal that background where a clear LEGO support shows in the shot.
