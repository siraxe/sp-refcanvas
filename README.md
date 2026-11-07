# RefCanvas

A reference-image dock panel for Adobe Substance 3D Painter. Drop or load
images onto a collapsible canvas, arrange them as transformable collage
layers, pick colours from the reference and push them straight into the
active paint tool's Base Color with `LIVE ON`. Pure Python, using the
Qt6/PySide6 binding on Painter 10.1 and newer and Qt5/PySide2 on earlier
builds. Swatches, colours, layout and the collage persist between
sessions.

## Hotkeys

<table>
  <tr>
    <th width="30%">Hotkey</th>
    <th width="70%">Preview</th>
  </tr>
  <tr>
    <td><b>Color Swap</b> &mdash; <code>Shift + X</code><br>(rebindable)</td>
    <td rowspan="6"><i>

https://github.com/user-attachments/assets/ccdb0242-8a47-46ed-a3c8-2dd43083dbcf

</i></td>
  </tr>
  <tr>
    <td><b>Transform Layer</b> &mdash; <code>Ctrl + T</code><br>(rebindable)</td>
  </tr>
  <tr>
    <td><b>Add Swatch</b> &mdash; <code>Alt + C</code><br>(rebindable)</td>
  </tr>
  <tr>
    <td><b>Fit Layers</b> &mdash; <code>Alt + F</code><br>(inside panel)</td>
  </tr>
  <tr>
    <td><b>Toggle LIVE ON</b> &mdash; <code>Alt + Z</code><br>(inside panel)</td>
  </tr>
  <tr>
    <td><b>Delete Layer</b> &mdash; <code>Delete</code><br>(panel focus)</td>
  </tr>
</table>

Rebindable shortcuts can be changed in `REFCANVAS Settings`, where all
hotkeys can also be switched off at once.

## Install

1. Download `refcanvas_plugin-0.1.0.zip` from the
   [releases page](https://github.com/siraxe/sp-refcanvas/releases).
2. Unzip it.
3. Copy the `refcanvas_plugin` folder into
   `%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\`.
4. Restart Painter; the `REFCANVAS` dock opens on startup.

## License

Released under the [MIT License](LICENSE).
