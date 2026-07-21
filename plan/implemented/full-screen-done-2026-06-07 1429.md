# full-screen

> **Status:** Draft  
> **Created:** 2026-06-07 12:15:28

## Overview
Implement a dedicated full-screen image viewer that allows users to browse photos in high detail, navigate through the album, and view extracted metadata as an overlay.

## Motivation
While the current detail modal provides a summary, it is not suitable for high-resolution visual inspection or a "gallery-like" browsing experience. A full-screen mode eliminates UI clutter and focuses on the imagery, making it easier to verify the quality of the LLM's extractions.

## Requirements
- **Entrance**: Provide a "Fullscreen" button in the existing photo detail modal.
- **Fullscreen View**:
  - A full-viewport modal with a black background.
  - The image should be centered and scaled to fit the screen while maintaining aspect ratio.
  - Close button (X) clearly visible in the top corner.
- **Navigation**:
  - Left and Right navigation arrows to cycle through images in the current folder.
  - Navigation should respect the order of images discovered by `PhotoList`.
- **Metadata Overlay**:
  - A toggleable (Show/Hide) overlay that displays the extracted `description`, `subjects`, and `tags`.
  - Overlay should be semi-transparent to not completely obscure the photo.
- **Responsiveness**: Ensure the viewer works on different screen resolutions and maintains the image's aspect ratio.

## Design / Approach
- **UI Component**: Use a `dbc.Modal` with a custom CSS class (or inline styles) to remove standard modal margins and set the background to black.
- **State Management**: 
  - Use a Dash `dcc.Store` to keep track of the current image index relative to the folder's image list.
  - When navigating "Next" or "Prev", update the index, resolve the image path, and refresh the image source and metadata overlay.
- **Image Serving**: Continue using the existing `/preview` Flask route for efficient thumbnail/preview generation.

### Files to modify
- `src/layout.py` - Add the full-screen modal to the main layout.
- `src/components.py` - Create `build_fullscreen_viewer()` and update `build_detail_modal_content()` to include the fullscreen trigger.
- `src/callbacks.py` - Implement the navigation logic (Next/Prev), the trigger for the fullscreen modal, and the metadata toggle.

### Database changes (if any)
None.

### API changes (if any)
None.

## Implementation Steps
1. **UI Layout**: Add the fullscreen modal and a `dcc.Store` for index tracking to `src/layout.py`.
2. **Trigger**: Add the "Fullscreen" button to the detail modal in `src/components.py`.
3. **Navigation Logic**: 
   - Implement callbacks in `src/callbacks.py` to handle "Next" and "Prev" buttons.
   - Ensure the logic correctly handles boundaries (start/end of list).
4. **Metadata Overlay**: Implement the toggle logic and layout for the semi-transparent metadata panel.
5. **Styling**: add custom CSS to ensure the modal occupies 100% of the viewport without borders.

## Testing Plan
- [ ] Manual test: Open detail modal -> Click Fullscreen -> Verify image scale and centering.
- [ ] Manual test: Use Next/Prev buttons to navigate through several images in a folder.
- [ ] Manual test: Toggle metadata overlay on/off and verify readability.
- [ ] Manual test: Close fullscreen and ensure it returns to the detail modal correctly.
- [ ] Verify that navigation works correctly with folders containing only one image.

## Edge Cases & Risks
- **Folder Change**: If the user changes the parent folder while in fullscreen, the viewer should either close or reset its index.
- **Empty/Single-Image Folders**: Navigation buttons should be disabled or behave gracefully.
- **Image Loading**: Ensure navigation transitions are smooth without excessive flickering during image source updates.

## References
- Existing `/preview` route in `app.py`.
- `PhotoList` discovery logic in `src/discovery.py`.
