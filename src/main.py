import os
import qrcode
import flet as ft
from flet_color_pickers import MaterialPicker
import base64
from io import BytesIO  
import asyncio
import PIL 
import urllib.parse
import random
import datetime

#Constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
ERROR_CORRECTION_MAP = {
    "L (7%)": qrcode.constants.ERROR_CORRECT_L,
    "M (15%)": qrcode.constants.ERROR_CORRECT_M,
    "Q (25%)": qrcode.constants.ERROR_CORRECT_Q,
    "H (30%)": qrcode.constants.ERROR_CORRECT_H,
}
APP_VERSION = "__VERSION__"

#Helper functions (take an input and return a value)
def normalize_picker_date(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone().date()

def hex_to_rgba(color_str):
    if color_str.startswith("#"):
        c = color_str.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        return (r, g, b, 255)
    else:   
        return PIL.ImageColor.getcolor(color_str, "RGBA")

def normalize_hex(color_str):
    if color_str.startswith("#"):
        c = color_str.lstrip("#")
        if len(c) == 8:  # AARRGGBB
            c = c[2:]
        return "#" + c
    else:
        r, g, b = PIL.ImageColor.getcolor(color_str, "RGB")
        return "#{:02x}{:02x}{:02x}".format(r, g, b)

def add_logo_aligned_to_grid(pil_img, logo_data, qr_obj, max_module_ratio=0.25, bg_color=(255, 255, 255, 255)):
    box_size = qr_obj.box_size
    border = qr_obj.border
    modules_count = len(qr_obj.get_matrix())

    max_logo_modules = int(modules_count * max_module_ratio)
    if max_logo_modules % 2 == 0:
        max_logo_modules -= 1
    max_logo_modules = max(max_logo_modules, 1)

    logo_size_px = max_logo_modules * box_size

    logo = PIL.Image.open(BytesIO(logo_data)).convert("RGBA")
    logo = logo.resize((logo_size_px, logo_size_px))

    qr_w, qr_h = pil_img.size
    pos_x = (qr_w - logo_size_px) // 2
    pos_y = (qr_h - logo_size_px) // 2

    pil_img = pil_img.convert("RGBA")
    backdrop = PIL.Image.new("RGBA", (logo_size_px, logo_size_px), bg_color)
    pil_img.paste(backdrop, (pos_x, pos_y))
    pil_img.paste(logo, (pos_x, pos_y), logo)
    return pil_img

def relative_luminance(hex_color):
    hex_color = hex_color.lstrip("#")
    r, g, b = [int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4)]
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def contrast_ratio(hex1, hex2):
    l1, l2 = relative_luminance(hex1), relative_luminance(hex2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)

#Lazy loading helper class

class LogoPicker:
    def __init__(self, page):
        self.page = page
        self.file_picker = ft.FilePicker()
        page.services.append(self.file_picker)
        page.update()

    async def pick(self, allowed_extensions=None):
        files = await self.file_picker.pick_files(
            allowed_extensions=allowed_extensions,
            with_data=True
        )
        return files[0] if files else None


class CreateBsHandle:
    """Wraps every local control built inside build_create_bs() as attributes,
    exposing .create_bs (the actual BottomSheet control) and a mirrored
    .open property so create_bs_ref["instance"].open = True/False works
    exactly like it did when create_layout was a module-level BottomSheet."""
    def __init__(self, create_layout, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.create_bs = create_layout

    @property
    def open(self):
        return self.create_bs.open

    @open.setter
    def open(self, value):
        self.create_bs.open = value

        
def main(page: ft.Page):
    ###PAGE SETTINGS--------------------------------------------------------------
    page.title = "QuickeR"
    
    #Instanced variables
    last_qr_image = {"img": None}
    _debounce_task = {"task": None}
    logo_image_path = {"path": None}
    logo_picker_ref = {"instance": None}
    about_bs_ref = {"instance": None}
    create_bs_ref = {"instance": None}
    
    ##THEMING--------------------------------------------------------------
    page.fonts = {
        "MaterialRounded":"GoogleSansFlex.ttf",
        "MaterialRoundedBold":"GoogleSansFlex-Bold.ttf"
        #"MaterialRoundedLight":"GoogleSansFlex-Light.ttf"
    }
    page.update()
    page.theme_mode = ft.ThemeMode.DARK

    #Picks a random theme color and a font
    def theme_selector():
        theme_colors = [
            ft.Colors.BLUE_600,
            ft.Colors.GREEN_600,
            ft.Colors.YELLOW_600,
            ft.Colors.ORANGE_600,
            ft.Colors.RED_600,
            ft.Colors.PURPLE_600,
            ft.Colors.PINK_600,
            ft.Colors.GREY_600
            #ft.Colors.GREY_100
        ]
        selected_theme = theme_colors[random.randint(0,(len(theme_colors)-1))]
        page.theme = ft.Theme(color_scheme_seed=selected_theme, font_family="MaterialRounded")
        page.update()
    theme_selector()

    #Swaps theme mode between light and dark
    def appearance_swapper():
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
        else:
            page.theme_mode = ft.ThemeMode.DARK
        page.update()

    ###MAIN FUNCTIONS--------------------------------------------------------------
    #Checks contrast between the two chosen colors and shows a warning if it's too low for reliable scanning
    def check_qr_contrast(fill, back):
        try:
            f_hex = normalize_hex(fill)
            b_hex = normalize_hex(back)
            ratio = contrast_ratio(f_hex, b_hex)
        except Exception:
            return
        if ratio < 2.0:
            return 1
        elif ratio < 2.5:
            return 2
        else:
            return False

    #Generates a QR code based on the input and displays it in the preview and summary area
    def display_preview_qr(url, qr_color_primary, qr_color_secondary, error_correct):
        if create_bs_ref["instance"] is not None:
            create_bs_ref["instance"].preview_qr_area.controls.clear()

        if logo_image_path["path"]:
            error_correct = qrcode.constants.ERROR_CORRECT_H

        def build_qr(fill, back):
            q = qrcode.QRCode(error_correction=error_correct, box_size=10, border=4)
            q.add_data(str(url))
            q.make(fit=True)
            img = q.make_image(fill_color=fill, back_color=back).convert("RGBA")
            return q, img

        fill_color, back_color = qr_color_primary, qr_color_secondary
        qr_obj, pil_img = build_qr(fill_color, back_color)

        if logo_image_path["path"]:
            pil_img = add_logo_aligned_to_grid(pil_img, logo_image_path["path"], qr_obj, max_module_ratio=0.22, bg_color=hex_to_rgba(qr_color_secondary))

        check_qr_contrast(qr_color_primary, qr_color_secondary)

        pil_img = pil_img.convert("RGB")
        last_qr_image["img"] = pil_img
        archivo_temporal_ram = BytesIO()
        pil_img.save(archivo_temporal_ram, format="PNG")
        base64_puro = base64.b64encode(archivo_temporal_ram.getvalue()).decode("utf-8")
        uri_base64 = f"data:image/png;base64,{base64_puro}"
        preview_qr = ft.Image(src=uri_base64, width=200, height=200, border_radius=10)
        preview_qr_on_summary.content = preview_qr
        if create_bs_ref["instance"] is not None:
            create_bs_ref["instance"].preview_qr_area.controls.append(preview_qr)
        page.update()
    file_saver = ft.FilePicker()
    page.services.append(file_saver)
    page.update()

    #Shows a dialog confirming the download and starts the download process, besides offering retries
    def show_download_confirm_dialog():
        if not filename_textfield.value:
            page.show_dialog(ft.AlertDialog(
                title=ft.Text("Missing filename"),
                content=ft.Text("Please enter a filename for the QR code."),
                actions=[ft.TextButton("OK", on_click=lambda e: page.pop_dialog())],
                actions_alignment="end",
            ))
        else:
            page.show_dialog(ft.AlertDialog(
                title=ft.Text("Download started!"),
                content=ft.Text(f"The qr code should download automatically.\n If it doesn't, please retry with the button below."),
                actions=[
                    ft.TextButton("Retry", on_click=lambda e: asyncio.ensure_future(download_qr())),
                    ft.TextButton("Got it!", on_click=lambda e: page.pop_dialog()),
                ],
                actions_alignment="end",
            ))
            asyncio.ensure_future(download_qr())
    
    #Downloads the qrs
    async def download_qr():
        if last_qr_image["img"] is None:
            return
        buf = BytesIO()
        last_qr_image["img"].save(buf, format="PNG")
        await file_saver.save_file(
            file_name=filename_textfield.value + ".png",
            allowed_extensions=["png"],
            src_bytes=buf.getvalue(),
        )
    
    #Opens the QR creation bottom sheet (lazy: builds it only the first time)
    def qr_creator_open():
        async def _open():
            if create_bs_ref["instance"] is None:
                create_bs_ref["instance"] = build_create_bs()
                page.overlay.append(create_bs_ref["instance"].create_bs)
                page.update()
                await asyncio.sleep(0.05)
                display_preview_qr("", "black", "white", ERROR_CORRECTION_MAP["M (15%)"])
            create_bs_ref["instance"].open = True
            page.update()
        page.run_task(_open)
    
    #Checks that everything is filled in before transitioning to summary view
    def input_checker():
        def alert_empty():
            page.show_dialog(ft.AlertDialog(
                title=ft.Text("Missing required fields"),
                content=ft.Text("Please fill in all required fields for the selected QR type."),
                actions=[ft.TextButton("OK", on_click=lambda e: page.pop_dialog())],
                actions_alignment="end",
            ))

        cb = create_bs_ref["instance"]
        if cb.qr_type_dropdown.value == "WIFI":
            if not cb.wifi_name.value:
                alert_empty()
                return False
            if cb.wifi_protocol_dropdown.value != "No password" and not cb.wifi_password.value:
                alert_empty()
                return False
        elif cb.qr_type_dropdown.value == "Email":
            if not cb.email_address.value:
                alert_empty()
                return False
        elif cb.qr_type_dropdown.value == "Phone":
            if not cb.phone_number.value or not cb.phone_prefix.value:
                alert_empty()
                return False
        elif cb.qr_type_dropdown.value == "SMS":
            if not cb.sms_number.value or not cb.sms_prefix.value or not cb.sms_message.value:
                alert_empty()
                return False
        elif cb.qr_type_dropdown.value == "Location":
            if not cb.location_lat.value or not cb.location_lng.value:
                alert_empty()
                return False
        elif cb.qr_type_dropdown.value == "Event":
            if not cb.event_title.value or not cb.event_location.value or not cb.date_picker.start_value or not cb.date_picker.end_value or not cb.start_time_picker.value or not cb.end_time_picker.value:
                alert_empty()
                return False
        else:  
            if not cb.qr_url_input_field.value:
                alert_empty()
                return False
        return True

    #Copies text to the clipboard
    async def copy_text_to_clipboard(text):
        await ft.Clipboard().set(text)
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Text copied"),
            content=ft.Text("The text has been copied to the clipboard."),
            actions=[ft.TextButton("OK", on_click=lambda e: page.pop_dialog())],
            actions_alignment="end",
        ))

    #Transitions to summary view
    def qr_create_triggered():
        cb = create_bs_ref["instance"]
        def perform_transition():
            type_icon.icon = get_logo()
            get_content()
            if create_button in overview.controls:
                overview.controls.remove(create_button)
                overview.controls.append(summary_visual)
            clean_create_bs_up()
        if input_checker():
            contrast_result = check_qr_contrast(cb.qr_color_scheme_primary.color, cb.qr_color_scheme_secondary.color)
            if contrast_result == 1:
                page.show_dialog(ft.AlertDialog(
                    title=ft.Text("Low contrast"),
                    content=ft.Text("The selected colors have low contrast. This may result in a QR code that is difficult to scan. Do you want to continue?"),
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                        ft.TextButton("Continue", on_click=lambda e: [page.pop_dialog(), perform_transition()]),
                    ],
                    actions_alignment="end",
                ))
            elif contrast_result == 2:
                page.show_dialog(ft.AlertDialog(
                    title=ft.Text("Moderate contrast"),
                    content=ft.Text("The selected colors have moderate contrast. This may result in a QR code that is difficult to scan. Do you want to continue?"),
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                        ft.TextButton("Continue", on_click=lambda e: [page.pop_dialog(), perform_transition()]),
                    ],
                    actions_alignment="end",
                ))
            else:
                perform_transition()

    #Picks the logo for the QR code and updates the preview
    async def pick_logo():
        if logo_picker_ref["instance"] is None:
            logo_picker_ref["instance"] = LogoPicker(page)
            page.update()
            await asyncio.sleep(0.2)
        file = await logo_picker_ref["instance"].pick(["png", "jpg", "jpeg"])
        if file and file.bytes:
            logo_image_path["path"] = file.bytes
            prop_changed()

    #Removes the logo from the QR code and updates the preview
    def remove_logo():
        logo_image_path["path"] = None
        prop_changed()

    #Returns the appropriate icon for the selected QR type
    def get_logo():
        cb = create_bs_ref["instance"]
        if cb.qr_type_dropdown.value == "WIFI":
            return ft.Icons.WIFI_ROUNDED
        elif cb.qr_type_dropdown.value == "URL/Link":
            return ft.Icons.LINK_ROUNDED
        elif cb.qr_type_dropdown.value == "Email":
            return ft.Icons.MAIL_ROUNDED
        elif cb.qr_type_dropdown.value == "Phone":
            return ft.Icons.CALL_ROUNDED
        elif cb.qr_type_dropdown.value == "SMS":
            return ft.Icons.MESSAGE_ROUNDED
        elif cb.qr_type_dropdown.value == "Location":
            return ft.Icons.PIN_ROUNDED
        elif cb.qr_type_dropdown.value == "Event":
            return ft.Icons.PARTY_MODE_ROUNDED
        elif cb.qr_type_dropdown.value == "Text":
            return ft.Icons.TEXT_FORMAT_ROUNDED   

    #Clears the summary view and goes back to the home view, resetting all input fields
    def clear_summary():
        def clear_summary_action():
            page.pop_dialog()
            if summary_visual in overview.controls:
                overview.controls.remove(summary_visual)
                overview.controls.append(create_button)
            clean_create_bs_up(full_reset=True)
            page.update()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Discard?"),
            alignment=ft.Alignment.CENTER,
            actions=[
                ft.TextButton("No", on_click=lambda e: page.pop_dialog()),
                ft.Button(icon=ft.Icons.DELETE, bgcolor=ft.Colors.RED_900, content="Yes", on_click=lambda e: clear_summary_action())],
            open=True))

    #Clears the QR creation bottom sheet and resets all input fields
    def clean_create_bs_up(full_reset=False):
        cb = create_bs_ref["instance"]
        if cb and cb.open == True:
            cb.open = False
        if full_reset and cb:
            for item in [
                cb.wifi_name, cb.wifi_password, cb.qr_url_input_field, cb.email_address, 
                cb.email_subject, cb.email_body, cb.phone_prefix, cb.phone_number, cb.sms_prefix, 
                cb.sms_number, cb.sms_message, cb.location_lat, cb.location_lng, cb.event_title, 
                cb.event_location, cb.start_time_picker, cb.end_time_picker
                ]:
                item.value = ""
        page.update()

    #Opens the about bottom sheet (lazy: builds it only the first time)
    def open_about_bs():
        async def _open_about():
            if about_bs_ref["instance"] is None:
                about_bs_ref["instance"] = build_about_bs()
                page.overlay.append(about_bs_ref["instance"])
                page.update()
                await asyncio.sleep(0.05)
            about_bs_ref["instance"].open = True
            page.update()
        page.run_task(_open_about)

    #Closes the about bottom sheet
    def clean_about_bs_up():
        if about_bs_ref["instance"] and about_bs_ref["instance"].open == True:
            about_bs_ref["instance"].open = False
        page.update()   

    #Sets the GitHub icon color based on the current theme mode and whether it should be inverted
    def get_github_icon_by_mode(invert=False):
        if invert:
            if page.theme_mode == ft.ThemeMode.DARK:
                return ft.Image("github-white-icon.webp",color="black",width=20,height=20)
            else:
                return ft.Image("github-white-icon.webp",color="white",width=20,height=20)
        else:
            if page.theme_mode == ft.ThemeMode.DARK:
                return ft.Image("github-white-icon.webp",color="white",width=20,height=20)
            else:
                return ft.Image("github-white-icon.webp",color="black",width=20,height=20)

    ###LAYOUTS AND CONTROLS--------------------------------------------------------------

    #appearance_setting = IconButton(icon=Icons.BRIGHTNESS_6_ROUNDED,on_click=lambda e: appearance_swapper()) -> unused

    ##MAIN LAYOUT --------------------------------------------------------------


    ##ABOUT BOTTOM SHEET (lazy-built) --------------------------------------------------------------
    def build_about_bs():
        about_bs = ft.BottomSheet(
            draggable=True,
            use_safe_area=True,
            scrollable=True,
            fullscreen=True,
            show_drag_handle=True,
            open=False,
            on_dismiss=lambda e: clean_about_bs_up(),
            content=
                ft.Column(
                    horizontal_alignment="center",
                    scroll=ft.ScrollMode.AUTO,
                    visible=True,
                    controls=[
                        ft.Container(
                            content=ft.Column(controls=[
                                ft.Row(alignment="center",controls=[
                                    ft.Text(value="QuickeR", size=40,font_family="MaterialRoundedBold", align=ft.Alignment.CENTER, color=ft.Colors.WHITE, style=ft.TextStyle(weight=ft.FontWeight.BOLD)),
                                    ft.Container(border_radius=10,bgcolor=ft.Colors.TERTIARY_CONTAINER,content=ft.Text(value="Web", size=15,font_family="MaterialRoundedBold", color=ft.Colors.WHITE, style=ft.TextStyle(weight=ft.FontWeight.BOLD)),margin=ft.Margin.only(left=5),border=ft.Border.all(width=3,color=ft.Colors.TERTIARY),padding=10)
                                ]),
                                ft.Text(value="Quick | Simple | Private | Open Source", size=15, align=ft.Alignment.CENTER, color=ft.Colors.GREY_400, style=ft.TextStyle(weight=ft.FontWeight.W_200))
                            ]),
                            padding=20,
                            bgcolor=ft.Colors.SECONDARY_CONTAINER,
                            border_radius=30,
                            width=page.width,
                            margin=ft.Margin.only(left=20, right=20, bottom=5)
                        ),
                        ft.ExpansionTile(
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                            collapsed_bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                            margin=ft.Margin.only(left=20, right=20, bottom=5),
                            shape=ft.RoundedRectangleBorder(side=ft.BorderSide(width=0), radius=20),
                            collapsed_shape=ft.RoundedRectangleBorder(side=ft.BorderSide(width=0), radius=20),
                            title=ft.Text(value="Support QuickeR", size=15, color=ft.Colors.WHITE,style=ft.TextStyle(weight=ft.FontWeight.BOLD)),
                            controls=[ft.Column(controls=[
                                ft.Container(
                                    margin=ft.Margin.only(left=10,right=10),
                                    border_radius=20,
                                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                                    padding=20,
                                    content=ft.Column(
                                        controls=[
                                            ft.Row(controls=[
                                                ft.Icon(icon=ft.Icons.PAYMENT_ROUNDED,color=ft.Colors.WHITE),
                                                ft.Text(value="Donate", size=25, color=ft.Colors.WHITE,style=ft.TextStyle(weight=ft.FontWeight.BOLD)),
                                                ft.Container(content=ft.Text(value="ONE TIME", size=10, color=ft.Colors.WHITE,style=ft.TextStyle(weight=ft.FontWeight.BOLD)),margin=ft.Margin.only(left=5),bgcolor=ft.Colors.TERTIARY_CONTAINER,border=ft.Border.all(width=3, color=ft.Colors.TERTIARY), border_radius=10, padding=5),
                                            ]),
                                            ft.Text(value="If you want to support the project, you can do so by donating via Buy Me a Coffee or GitHub Sponsors.", size=15, color=ft.Colors.WHITE),
                                            ft.Row(alignment=ft.MainAxisAlignment.CENTER,controls=ft.Row(wrap=True,controls=[
                                                ft.Button(
                                                    margin=ft.Margin.only(top=10),
                                                    content=ft.Text(value="Buy Me a Coffee"),
                                                    icon=ft.Icons.COFFEE_ROUNDED, 
                                                    #on_click=lambda e: asyncio.ensure_future(open_url("https://www.buymeacoffee.com/ChoiceZero","BLANK")),
                                                    style=ft.ButtonStyle(
                                                        shape=ft.RoundedRectangleBorder(radius=12),
                                                        padding=10,
                                                        bgcolor=ft.Colors.PRIMARY,
                                                        color=ft.Colors.SURFACE,
                                                        overlay_color=ft.Colors.ON_PRIMARY_CONTAINER
                                                    ),
                                                ),
                                                ft.Button(
                                                    margin=ft.Margin.only(top=10),
                                                    content=ft.Text(value="GitHub Sponsors"),
                                                    icon=ft.CupertinoIcons.HEART_FILL, 
                                                    #on_click=lambda e: asyncio.ensure_future(open_url("https://www.buymeacoffee.com/ChoiceZero","BLANK")),
                                                    style=ft.ButtonStyle(
                                                        shape=ft.RoundedRectangleBorder(radius=12),
                                                        padding=10,
                                                        bgcolor=ft.Colors.PRIMARY,
                                                        color=ft.Colors.SURFACE,
                                                        overlay_color=ft.Colors.ON_PRIMARY_CONTAINER
                                                    ),
                                                )
                                            ]))
                                        ]
                                    )
                                ),
                                ft.Container(
                                    border_radius=20,
                                    margin=ft.Margin.only(left=10,right=10),
                                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                                    padding=20,
                                    content=ft.Column(
                                        controls=[
                                            ft.Row(controls=[
                                                ft.Icon(icon=ft.Icons.CODE_ROUNDED,color=ft.Colors.WHITE),
                                                ft.Text(value="Contribute", size=25, color=ft.Colors.WHITE,style=ft.TextStyle(weight=ft.FontWeight.BOLD)),
                                            ]),
                                            ft.Text(value="Contribute code or report bugs in order to improve the project as a community effort.", size=15, color=ft.Colors.WHITE),
                                            ft.Row(alignment=ft.MainAxisAlignment.CENTER,controls=[
                                                ft.Button(
                                                    align=ft.Alignment.CENTER,
                                                    margin=ft.Margin.only(top=10),
                                                    content=ft.Text(value="QuickeR-Web"),
                                                    icon=get_github_icon_by_mode(True), 
                                                    on_click=lambda e: asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web","BLANK")),
                                                    style=ft.ButtonStyle(
                                                        shape=ft.RoundedRectangleBorder(radius=12),
                                                        padding=10,
                                                        bgcolor=ft.Colors.PRIMARY,
                                                        color=ft.Colors.SURFACE,
                                                        overlay_color=ft.Colors.ON_PRIMARY_CONTAINER
                                                    ),
                                                ),
                                                ft.Button(
                                                    content=ft.Text(value="Report a bug"),
                                                    icon=ft.Icons.BUG_REPORT_ROUNDED,
                                                    margin=ft.Margin.only(top=10),
                                                    on_click=lambda e: asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web/issues","BLANK")),
                                                    style=ft.ButtonStyle(
                                                        shape=ft.RoundedRectangleBorder(radius=12),
                                                        padding=10,
                                                        bgcolor=ft.Colors.PRIMARY,
                                                        color=ft.Colors.SURFACE,
                                                        overlay_color=ft.Colors.ON_PRIMARY_CONTAINER
                                                    ),
                                                )
                                            ])   
                                        ]
                                    )
                                ),
                                ft.Container(
                                    border_radius=20,
                                    margin=ft.Margin.only(left=10,right=10,bottom=10),
                                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                                    padding=20,
                                    content=ft.Column(
                                        controls=[
                                            ft.Row(controls=[
                                                ft.Icon(icon=ft.Icons.SHARE_ROUNDED,color=ft.Colors.WHITE),
                                                ft.Text(value="Share the app", size=25, color=ft.Colors.WHITE,style=ft.TextStyle(weight=ft.FontWeight.BOLD)),
                                            ]),
                                            ft.Text(value="Help spread the word about the app and recommend it to others. The more users, the more interest in the project!", size=15, color=ft.Colors.WHITE),
                                            ft.Button(
                                                align=ft.Alignment.CENTER,
                                                content=ft.Text(value="Copy link to clipboard"),
                                                icon=ft.Icons.COPY_ALL_ROUNDED,
                                                margin=ft.Margin.only(top=10),
                                                on_click=lambda e: asyncio.ensure_future(copy_text_to_clipboard("https://choicezero.github.io/QuickeR-Web/")),
                                                style=ft.ButtonStyle(
                                                    shape=ft.RoundedRectangleBorder(radius=12),
                                                    padding=10,
                                                    bgcolor=ft.Colors.PRIMARY,
                                                    color=ft.Colors.SURFACE,
                                                    overlay_color=ft.Colors.ON_PRIMARY_CONTAINER
                                                ),
                                            )
                                        ]
                                    )
                                ),
                            ])]
                        ),
                        ft.Text(value="General information", size=17, color=ft.Colors.WHITE, margin=ft.Margin.only(left=20, right=20, top=15)),
                        ft.Container(
                            width=page.width,
                            border_radius=20,
                            padding=20,
                            margin=ft.Margin.only(left=20, right=20, bottom=5),
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                            content=ft.Column(controls=[
                                ft.Row(controls=[
                                    ft.Icon(icon=ft.Icons.NUMBERS_ROUNDED, size=15, color=ft.Colors.PRIMARY),
                                    ft.Text(value=("Version"), size=15, color=ft.Colors.GREY_400),
                                    ft.Container(expand=True),
                                    ft.Text(value=APP_VERSION, size=15, color=ft.Colors.PRIMARY)
                                ]),
                                ft.Divider(color=ft.Colors.SURFACE_CONTAINER_LOW,thickness=2),
                                ft.Row(controls=[
                                    ft.Icon(icon=ft.Icons.LIBRARY_BOOKS_ROUNDED, size=15, color=ft.Colors.PRIMARY),
                                    ft.Text(value=("License"), size=15, color=ft.Colors.GREY_400),
                                    ft.Container(expand=True),
                                    ft.Text(value="MIT License", size=15, color=ft.Colors.PRIMARY)
                                ]), 
                                ft.Divider(color=ft.Colors.SURFACE_CONTAINER_LOW,thickness=2),
                                ft.Row(wrap=True,alignment=ft.MainAxisAlignment.SPACE_BETWEEN,controls=[
                                    ft.Row(controls=[
                                        ft.Icon(icon=ft.Icons.PERSON_2_ROUNDED, size=15, color=ft.Colors.PRIMARY),
                                        ft.Text(value=("Developed by"), size=15, color=ft.Colors.GREY_400),
                                    ]),
                                    ft.Text(value="Unax Martinez Llorente (aka ChoiceZero).", size=15, color=ft.Colors.WHITE)
                                ]),
                            ])
                        ),
                        ft.Text(value="Links", size=17, color=ft.Colors.WHITE, margin=ft.Margin.only(left=20, right=20, top=15)),
                        ft.Container(
                            width=page.width,
                            border_radius=20,
                            padding=20,
                            margin=ft.Margin.only(left=20, right=20, bottom=5),
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                            content=ft.Column(controls=[
                                ft.Row(controls=[
                                    ft.Icon(icon=ft.Icons.INSERT_LINK_ROUNDED, size=15, color=ft.Colors.PRIMARY),
                                    ft.Text(value=("Repository"), size=15, color=ft.Colors.GREY_400),
                                    ft.Container(expand=True),
                                    ft.Button(
                                        content=ft.Text(value="QuickeR-Web"),
                                        icon=get_github_icon_by_mode(True), 
                                        on_click=lambda e: asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web","BLANK")),
                                        style=ft.ButtonStyle(
                                            shape=ft.RoundedRectangleBorder(radius=12),
                                            padding=10,
                                            bgcolor=ft.Colors.PRIMARY,
                                            color=ft.Colors.SURFACE,
                                            overlay_color=ft.Colors.ON_PRIMARY_CONTAINER
                                        ),
                                    )
                                ]),
                                ft.Divider(color=ft.Colors.SURFACE_CONTAINER_LOW, thickness=2),
                                ft.Row(controls=[
                                    ft.Icon(icon=ft.Icons.INSERT_LINK_ROUNDED, size=15, color=ft.Colors.PRIMARY),
                                    ft.Text(value=("Bugs"), size=15, color=ft.Colors.GREY_400),
                                    ft.Container(expand=True),
                                    ft.Button(
                                        content=ft.Text(value="Report a bug"),
                                        icon=ft.Icons.BUG_REPORT_ROUNDED,
                                        on_click=lambda e: asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web","BLANK")),
                                        style=ft.ButtonStyle(
                                            shape=ft.RoundedRectangleBorder(radius=12),
                                            padding=10,
                                            bgcolor=ft.Colors.PRIMARY,
                                            color=ft.Colors.SURFACE,
                                            overlay_color=ft.Colors.ON_PRIMARY_CONTAINER
                                        ),
                                    )
                                ]),
                                ft.Divider(color=ft.Colors.SURFACE_CONTAINER_LOW, thickness=2),
                                ft.Row(controls=[
                                    ft.Icon(icon=ft.Icons.INSERT_LINK_ROUNDED, size=15, color=ft.Colors.PRIMARY),
                                    ft.Text(value=("Release notes"), size=15, color=ft.Colors.GREY_400),
                                    ft.Container(expand=True),
                                    ft.Button(
                                        content=ft.Text(value="Release notes"),
                                        icon=ft.Icons.NEW_RELEASES_ROUNDED,
                                        on_click=lambda e: asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web/releases","BLANK")),
                                        style=ft.ButtonStyle(
                                            shape=ft.RoundedRectangleBorder(radius=12),
                                            padding=10,
                                            bgcolor=ft.Colors.PRIMARY,
                                            color=ft.Colors.SURFACE,
                                            overlay_color=ft.Colors.ON_PRIMARY_CONTAINER
                                        ),
                                    )
                                ]),
                            ])
                        ),
                        ft.Text(value="Privacy", size=17, color=ft.Colors.WHITE, margin=ft.Margin.only(left=20, right=20, top=15)),
                        ft.Container(
                            width=page.width,
                            border_radius=20,
                            padding=20,
                            margin=ft.Margin.only(left=20, right=20, bottom=5),
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                            content=ft.Column(controls=[
                                ft.Row(wrap=True,alignment=ft.MainAxisAlignment.SPACE_BETWEEN,controls=[
                                    ft.Row(controls=[
                                        ft.Icon(icon=ft.Icons.DISABLED_VISIBLE_ROUNDED, size=15, color=ft.Colors.PRIMARY),
                                        ft.Text(value=("Private"), size=15, color=ft.Colors.GREY_400),
                                    ]),
                                    ft.Text(value="No telemetry or analytics are used.", size=15, color=ft.Colors.WHITE)  
                                ]),
                                ft.Divider(color=ft.Colors.SURFACE_CONTAINER_LOW,thickness=2),
                                ft.Row(wrap=True,alignment=ft.MainAxisAlignment.SPACE_BETWEEN,controls=[
                                    ft.Row(controls=[
                                        ft.Icon(icon=ft.Icons.EDIT_ROUNDED, size=15, color=ft.Colors.PRIMARY),
                                        ft.Text(value=("Open source"), size=15, color=ft.Colors.GREY_400),
                                    ]),
                                    ft.Text(value="Fully open source and auditable.", size=15, color=ft.Colors.WHITE)  
                                ]),
                                ft.Divider(color=ft.Colors.SURFACE_CONTAINER_LOW,thickness=2),
                                ft.Row(wrap=True,alignment=ft.MainAxisAlignment.SPACE_BETWEEN,controls=[
                                    ft.Row(controls=[
                                        ft.Icon(icon=ft.Icons.VERIFIED_USER_ROUNDED, size=15, color=ft.Colors.PRIMARY),
                                        ft.Text(value=("Personal"), size=15, color=ft.Colors.GREY_400),
                                    ]),
                                    ft.Text(value="No private data is collected or stored.", size=15, color=ft.Colors.WHITE)
                                ]),
                            ])
                        ),
                        ft.Row(alignment=ft.MainAxisAlignment.CENTER,controls=[ft.Text(value="Made with ❤️ in Spain.", size=15, color=ft.Colors.GREY_400)]),
                        ft.Text(value="© 2026 Unax Martinez Llorente.", size=15, color=ft.Colors.GREY_400),
                        ft.Container(height=50),    
                    ]
                )
            )
        return about_bs   
        
    ##CREATE BOTTOM SHEET (lazy-built) --------------------------------------------------------------
    def build_create_bs():
        qr_type_dropdown = ft.Dropdown(border_radius=50,fill_color=ft.Colors.SURFACE_CONTAINER_LOW,filled=True,on_select=lambda e: type_trigger(e),border_width=0,value="URL/Link",options=[
            ft.DropdownOption(text="URL/Link",leading_icon=ft.Icons.LINK_ROUNDED),
            ft.DropdownOption(text="Text",leading_icon=ft.Icons.TEXT_FIELDS_ROUNDED),
            ft.DropdownOption(text="WIFI",leading_icon=ft.Icons.WIFI_ROUNDED),
            ft.DropdownOption(text="Email",leading_icon=ft.Icons.MAIL_OUTLINE_ROUNDED),
            ft.DropdownOption(text="Phone",leading_icon=ft.Icons.PHONE_ANDROID_ROUNDED),
            ft.DropdownOption(text="Location",leading_icon=ft.Icons.PIN_DROP_ROUNDED),
            ft.DropdownOption(text="SMS",leading_icon=ft.Icons.MESSAGE_ROUNDED),
            ft.DropdownOption(text="Event",leading_icon=ft.Icons.STAR_BORDER_ROUNDED),
        ])

        #URL
        url_protocol_dropdown = ft.Dropdown(border_radius=50,fill_color=ft.Colors.SURFACE_CONTAINER_LOW,filled=True,value="https://",border_width=0,options=[
            ft.DropdownOption(text="https://"),
            ft.DropdownOption(text="http://"),
            ])

        #WIFI
        wifi_name= ft.TextField(
            expand=True,
            border_width=0,
            label="Enter network name",
            on_change=lambda e: prop_changed()
        )

        wifi_protocol_dropdown = ft.Dropdown(border_radius=50,fill_color=ft.Colors.SURFACE_CONTAINER_LOW,filled=True,value="WPA2",border_width=0,on_select=lambda e: wifi_protocol_changed(e),options=[
            ft.DropdownOption(text="WPA2"),
            ft.DropdownOption(text="WPA"),
            ft.DropdownOption(text="WEP"),
            ft.DropdownOption(text="No password"),
        ])

        def wifi_protocol_changed(e):
            selected = e.control.value 
            if selected == "No password":
                wifi_password_setting.visible = False
            else:
                wifi_password_setting.visible = True
            prop_changed()

        wifi_password= ft.TextField(
            expand=True,
            border_width=0,
            label="Enter network password",
            on_change=lambda e: prop_changed()
        )

        wifi_password_setting= ft.Column(visible=True,controls=[
            ft.Divider(color=ft.Colors.GREY),
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[
                ft.Icon(icon=ft.Icons.PASSWORD_ROUNDED),
                ft.Text(value=("WIFI password"), size=20),
            ]),
            ft.Container(border_radius=10,bgcolor=ft.Colors.SURFACE_CONTAINER,content=wifi_password),
        ])

        wifi_area = ft.Column(visible=False,controls=[
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[
                ft.Icon(icon=ft.Icons.TEXT_FIELDS_ROUNDED),
                ft.Text(value=("Network name"), size=20),
            ]),
            ft.Container(border_radius=10,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                content=wifi_name
            ),
            ft.Divider(color=ft.Colors.GREY),
            ft.Container(
                content=ft.Row(controls=[
                    ft.Icon(icon=ft.Icons.INFO_OUTLINE_ROUNDED,color=ft.    Colors.WHITE),
                    ft.Container(expand=True,content=ft.Text(
                        value="If your network has no password, select it here!",
                        size=16,
                        color=ft.Colors.WHITE
                    )),
                    ],
                ),
                padding=15,
                bgcolor=ft.Colors.INVERSE_PRIMARY,border_radius=30,
                margin=ft.Margin.only(left=0, right=0, top=5, bottom=5,)
            ),
            ft.Row(wrap=True,alignment=ft.MainAxisAlignment.SPACE_BETWEEN,controls=[
                ft.Row(controls=[
                    ft.Icon(icon=ft.Icons.SHIELD),
                    ft.Text(value=("WIFI security protocol"), size=20),
                ]),
                wifi_protocol_dropdown
            ]),
            wifi_password_setting
        ])

        # Email
        email_address = ft.TextField(expand=True,border_width=0,label="Enter address",hint_text="Enter address",on_change=lambda e: prop_changed())
        email_adv_checkbox = ft.Switch(value=False, on_change=lambda e: email_checkbox_changed())
        email_general_content=ft.Column(visible=False,controls=[
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[
                ft.Icon(icon=ft.Icons.MAIL_ROUNDED),
                ft.Text(value=("Address"), size=20),
            ]),
            ft.Container(border_radius=10,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                content=email_address
            ),
            ft.Divider(color=ft.Colors.GREY),
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[
                ft.Icon(icon=ft.Icons.TEXT_FIELDS_ROUNDED),
                ft.Text(value=("Advanced options"), size=20),
                email_adv_checkbox
            ]),
        ])

        # -> On checkbox changed
        def email_checkbox_changed():
            if email_adv_checkbox.value:
                email_adv_content.visible = True
            else:
                email_adv_content.visible = False
            prop_changed()

        email_subject = ft.TextField(expand=True, border_width=0, label="Subject", on_change=lambda e: prop_changed())
        email_body = ft.TextField(expand=True, border_width=0, label="Body", multiline=True, on_change=lambda e: prop_changed())
        email_adv_content = ft.Column(visible=False, controls=[
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[ft.Icon(icon=ft.Icons.SUBJECT_ROUNDED), ft.Text(value="Subject", size=20)]),
            ft.Container(border_radius=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=email_subject),
            ft.Divider(color=ft.Colors.GREY),
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[ft.Icon(icon=ft.Icons.TEXT_FIELDS_ROUNDED), ft.Text(value="Body", size=20)]),
            ft.Container(border_radius=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=email_body),
        ])

        # Phone
        phone_prefix = ft.TextField(
            border_width=0,
            label="",
            hint_text="",
            width=80,
            max_length=4,
            counter=ft.Container(),
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: prop_changed()
        )
        phone_number = ft.TextField(
            expand=True,
            border_width=0,
            label="Enter address",
            hint_text="",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: prop_changed()
        )   
        phone_general_content=ft.Column(visible=False,controls=[
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[
                ft.Icon(icon=ft.Icons.CALL_ROUNDED),
                ft.Text(value=("Phone number"), size=20),
            ]),
            ft.Row(
                expand=True,
                controls=[
                ft.Container(
                    border_radius=10,
                    bgcolor=ft.Colors.SURFACE_CONTAINER,
                    content=ft.Row(controls=[
                        ft.Text("+",margin=ft.Margin(left=15),size=15),
                        phone_prefix
                    ])
                ),
                ft.Container(
                    expand=True,
                    border_radius=10,
                    bgcolor=ft.Colors.SURFACE_CONTAINER,
                    content=phone_number
                ),
            ])
        ]) 

        # SMS
        sms_prefix = ft.TextField(
            border_width=0,
            label="",
            hint_text="",
            width=80,
            max_length=4,
            counter=ft.Container(),
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: prop_changed()
        )
        sms_number = ft.TextField(
            expand=True,
            border_width=0,
            label="Enter phone number",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: prop_changed()
        )
        sms_message = ft.TextField(expand=True, border_width=0, label="Enter message", multiline=True, on_change=lambda e: prop_changed())

        sms_general_content = ft.Column(visible=False, controls=[
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[ft.Icon(icon=ft.Icons.SMS_ROUNDED), ft.Text(value="Phone number", size=20)]),
            ft.Row(controls=[
                ft.Container(
                    border_radius=10,
                    bgcolor=ft.Colors.SURFACE_CONTAINER,
                    content=ft.Row(controls=[ft.Text("+", margin=ft.Margin(left=15), size=15), sms_prefix])
                ),
                ft.Container(border_radius=10, expand=True, bgcolor=ft.Colors.SURFACE_CONTAINER, content=sms_number),
            ]),
            ft.Divider(color="grey"),
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[ft.Icon(icon=ft.Icons.MESSAGE_ROUNDED), ft.Text(value="Message", size=20)]),
            ft.Container(border_radius=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=sms_message),
        ])

        # Location
        location_lat = ft.TextField(expand=True, border_width=0, label="Latitude", keyboard_type=ft.KeyboardType.NUMBER, on_change=lambda e: prop_changed())
        location_lng = ft.TextField(expand=True, border_width=0, label="Longitude", keyboard_type=ft.KeyboardType.NUMBER, on_change=lambda e: prop_changed())

        location_general_content = ft.Column(visible=False, controls=[
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[ft.Icon(icon=ft.Icons.PIN_DROP_ROUNDED), ft.Text(value="Coordinates", size=20)]),
            ft.Row(controls=[
                ft.Container(border_radius=10, expand=True, bgcolor=ft.Colors.SURFACE_CONTAINER, content=location_lat),
                ft.Container(border_radius=10, expand=True, bgcolor=ft.Colors.SURFACE_CONTAINER, content=location_lng),
            ]),
        ])

        # Event (vCalendar/iCal)
        event_title = ft.TextField(expand=True, border_width=0, label="Event title", on_change=lambda e: prop_changed())
        event_location = ft.TextField(expand=True, border_width=0, label="Location", on_change=lambda e: prop_changed())

        date_picker = ft.DateRangePicker(open=False, on_change=lambda e: prop_changed())
        start_time_picker = ft.TimePicker(open=False, on_change=lambda e: prop_changed())
        end_time_picker = ft.TimePicker(open=False, on_change=lambda e: prop_changed())

        page.overlay.append(date_picker)
        page.overlay.append(start_time_picker)
        page.overlay.append(end_time_picker)

        def open_date_picker(e):
            date_picker.open = True
            page.update()

        def open_start_time(e):
            start_time_picker.open = True
            page.update()

        def open_end_time(e):
            end_time_picker.open = True
            page.update()

        date_picker_button = ft.Button(content="Date period",icon=ft.Icons.CALENDAR_MONTH_ROUNDED, on_click=lambda e: open_date_picker(e), style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), bgcolor={"": ft.Colors.SURFACE_CONTAINER}), tooltip="Pick date range")
        start_time_picker_button = ft.Button(content="Start time",icon=ft.Icons.ACCESS_TIME_ROUNDED, on_click=lambda e: open_start_time(e), style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), bgcolor={"": ft.Colors.SURFACE_CONTAINER}), tooltip="Pick start time")
        end_time_picker_button = ft.Button(content="End time",icon=ft.Icons.ACCESS_TIME_ROUNDED, on_click=lambda e: open_end_time(e), style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), bgcolor={"": ft.Colors.SURFACE_CONTAINER}), tooltip="Pick end time")

        event_general_content = ft.Column(visible=False, controls=[
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[ft.Icon(icon=ft.Icons.STAR_BORDER_ROUNDED), ft.Text(value="Event title", size=20)]),
            ft.Container(border_radius=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=event_title),
            ft.Divider(color="grey"),
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[ft.Icon(icon=ft.Icons.PIN_DROP_ROUNDED), ft.Text(value="Location", size=20)]),
            ft.Container(border_radius=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=event_location),
            ft.Divider(color="grey"),
            ft.Row(alignment=ft.MainAxisAlignment.START,controls=[ft.Icon(icon=ft.Icons.ACCESS_TIME_ROUNDED), ft.Text(value="Date and time", size=20)]),
            ft.Container(
                content=ft.Row(controls=[
                    ft.Icon(icon=ft.Icons.INFO_OUTLINE_ROUNDED,color=ft.Colors.WHITE),
                    ft.Container(expand=True,content=ft.Text(
                        value="Please change all fields below here!",
                        size=16,
                        color=ft.Colors.WHITE
                    )),
                    ],
                ),
                padding=15,
                bgcolor=ft.Colors.INVERSE_PRIMARY,border_radius=30,
                margin=ft.Margin.only(left=0, right=0, top=5, bottom=5,)
            ),
            ft.Row(wrap=True,alignment=ft.MainAxisAlignment.SPACE_BETWEEN,controls=[
                date_picker_button,
                start_time_picker_button,
                end_time_picker_button,
            ]),
        ])

        qr_url_input_field = ft.TextField(expand=True,border_width=0,label="Enter URL or text",on_change=lambda e: prop_changed())
        error_correction_dropdown = ft.Dropdown(border_radius=50,fill_color=ft.Colors.SURFACE_CONTAINER_LOW,filled=True,value="M (15%)",border_width=0,on_select=lambda e: prop_changed(),options=[
            ft.DropdownOption(text="L (7%)"),
            ft.DropdownOption(text="M (15%)"),
            ft.DropdownOption(text="Q (25%)"),
            ft.DropdownOption(text="H (30%)"),
            ])
        qr_color_scheme_primary = MaterialPicker(on_color_change=lambda e:prop_changed(),color="black")
        qr_color_scheme_secondary = MaterialPicker(on_color_change=lambda e:prop_changed(),color="white")

        preview_qr_area= ft.Row(controls=[], alignment=ft.MainAxisAlignment.CENTER,expand=False, tight=True)

        input_row = ft.Column(controls=[
            ft.Row(controls=[
                ft.Icon(icon=ft.Icons.SHORT_TEXT_ROUNDED),
                ft.Text(value=("Content"), size=20)
            ]),
            ft.Row(visible=True,controls=[
                url_protocol_dropdown,
                ft.Container(border_radius=10,expand=True,bgcolor=ft.Colors.SURFACE_CONTAINER,content=qr_url_input_field),
            ]),
        ])

        create_layout= ft.BottomSheet(draggable=False,use_safe_area=True,scrollable=False,fullscreen=True,open=False,on_dismiss=lambda e: clean_create_bs_up(),content=
            ft.Column(horizontal_alignment="center",scroll=ft.ScrollMode.AUTO,controls=[
                ft.Container(bgcolor=ft.Colors.INVERSE_PRIMARY,border_radius=30,expand=False,content=preview_qr_area,padding=20,),
                ft.Container(bgcolor=ft.Colors.SECONDARY_CONTAINER,border_radius=30,margin=ft.Margin.only(left=20, right=20, top=5, bottom=5),padding=20,content=
                    ft.Row(alignment="center",controls=[
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            expand=True, 
                            on_click=lambda e: clean_create_bs_up(),    
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=12),
                                bgcolor={"": ft.Colors.RED_500}, 
                            )
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CHECK,
                            expand=True,
                            on_click=lambda e: qr_create_triggered(), 
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=12),
                                bgcolor={"": ft.Colors.INVERSE_PRIMARY}, 
                            )
                        ),
                    ])
                ),
                ft.Container(bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,border_radius=30,margin=ft.Margin.only(left=20, right=20, top=5, bottom=5),padding=20,content=
                    ft.Column(controls=[
                        ft.Row(tight=True,col={"xs": 12, "lg": 3}, controls=[
                            ft.Icon(icon=ft.Icons.ARROW_DROP_DOWN_CIRCLE_OUTLINED),
                            ft.Text(value=("QR Type"), size=20),
                        ]),
                        ft.Container(col={"xs": 12, "lg": 2},content=qr_type_dropdown),
                        ft.Divider(color="grey"),
                        wifi_area,
                        input_row,
                        email_general_content,
                        email_adv_content,
                        phone_general_content,
                        sms_general_content,
                        location_general_content,
                        event_general_content,
                        ft.Divider(color="grey"),
                        ft.Row(wrap=True,alignment=ft.MainAxisAlignment.SPACE_BETWEEN,controls=[
                            ft.Row(controls=[
                                ft.Icon(icon=ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED),
                                ft.Text(value=("Error correction level"), size=20),
                            ]),
                            error_correction_dropdown
                        ]), 
                    ])
                ),
                ft.Text(value="Customization", size=18,color=ft.Colors.PRIMARY),
                ft.Container(bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,border_radius=30,margin=ft.Margin.only(left=20, right=20, top=5, bottom=5),padding=20,content=
                    ft.Column(controls=[
                        ft.Row(controls=[ft.Icon(icon=ft.Icons.ADD_PHOTO_ALTERNATE_ROUNDED),ft.Text(value=("Logo/Branding"), size=20)]),
                        ft.Container(
                            content=ft.Row(controls=[
                                ft.Icon(icon=ft.Icons.ERROR_OUTLINE_ROUNDED,color=ft.Colors.WHITE),
                                ft.Container(expand=True,content=ft.Text(
                                    value="As logos take up a big chunk of the QR's area, scanability may be greatly reduced. Thus, it is highly recommended that H level error correction is used.",
                                    size=16,
                                    color=ft.Colors.WHITE
                                )),
                                ],
                            ),
                            padding=15,
                            bgcolor=ft.Colors.RED_500,border_radius=30,
                            margin=ft.Margin.only(left=0, right=0, top=5, bottom=5,)
                        ),
                        ft.Row(wrap=True,alignment=ft.MainAxisAlignment.SPACE_BETWEEN,controls=[
                            ft.Button(content="Pick image from folder",icon=ft.Icons.FOLDER_COPY_ROUNDED, on_click=lambda e: asyncio.ensure_future(pick_logo())),
                            ft.Button(content="Remove logo",icon=ft.Icons.DELETE_ROUNDED, on_click=lambda e: remove_logo()),
                        ]),
                        ft.Divider(color="grey"),
                        ft.Text(value=("Color scheme"), size=20, color=ft.Colors.PRIMARY),
                        ft.ExpansionTile(title="Primary color:",controls=qr_color_scheme_primary,shape=ft.RoundedRectangleBorder(side=ft.BorderSide(width=0), radius=20),collapsed_shape=ft.RoundedRectangleBorder(side=ft.BorderSide(width=0), radius=20)),
                        ft.ExpansionTile(title="Background color:",controls=qr_color_scheme_secondary,shape=ft.RoundedRectangleBorder(side=ft.BorderSide(width=0), radius=20),collapsed_shape=ft.RoundedRectangleBorder(side=ft.BorderSide(width=0), radius=20)),
                    ])
                ),
                ft.Container(height=50)
            ]),
        )

        # --- Lazy-load capture: wrap every local control built above into a
        # handle object so the rest of the app can access them through
        # create_bs_ref["instance"].<name>, exactly as if they were module-level. ---
        handle = CreateBsHandle(create_layout, **{
            k: v for k, v in locals().items()
            if k not in ("create_layout",)
        })
        return handle

    def prop_changed():
        if _debounce_task["task"] is not None:
            _debounce_task["task"].cancel()
        _debounce_task["task"] = page.run_task(_debounced_update)

    async def _debounced_update():
        await asyncio.sleep(0.3)
        cb = create_bs_ref["instance"]
        if cb is None:
            return

        color_raw_1 = cb.qr_color_scheme_primary.color  
        if color_raw_1 and color_raw_1.startswith("#") and len(color_raw_1) == 9:
            color_rgb_1 = "#" + color_raw_1[3:] 
        else:
            color_rgb_1 = color_raw_1

        color_raw_2 = cb.qr_color_scheme_secondary.color  
        if color_raw_2 and color_raw_2.startswith("#") and len(color_raw_2) == 9:
            color_rgb_2 = "#" + color_raw_2[3:] 
        else:
            color_rgb_2 = color_raw_2

        error_correction = ERROR_CORRECTION_MAP.get(cb.error_correction_dropdown.value, qrcode.constants.ERROR_CORRECT_M)

        if cb.qr_type_dropdown.value == "WIFI":
            if cb.wifi_protocol_dropdown.value != "No password":
                cb.qr_url_input_field.value = f"WIFI:S:{cb.wifi_name.value};T:{cb.wifi_protocol_dropdown.value};P:{cb.wifi_password.value};;"
            else:
                cb.qr_url_input_field.value = f"WIFI:S:{cb.wifi_name.value};T:nopass;;"
            display_preview_qr(cb.qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)
        elif cb.qr_type_dropdown.value == "URL/Link":
                if cb.url_protocol_dropdown.value == "https://":
                    create_val = "https://"+cb.qr_url_input_field.value
                else:
                    create_val = "http://"+cb.qr_url_input_field.value
                display_preview_qr(create_val, color_rgb_1, color_rgb_2, error_correction)
        elif cb.qr_type_dropdown.value == "Email":
            if cb.email_adv_checkbox.value:
                params = []
                if cb.email_subject.value:
                    params.append(f"subject={urllib.parse.quote(cb.email_subject.value)}")
                if cb.email_body.value:
                    params.append(f"body={urllib.parse.quote(cb.email_body.value)}")
                query = "&".join(params)
                cb.qr_url_input_field.value = f"mailto:{cb.email_address.value}" + (f"?{query}" if query else "")
            else:
                cb.qr_url_input_field.value = f"mailto:{cb.email_address.value}"
            display_preview_qr(cb.qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)

        elif cb.qr_type_dropdown.value == "Phone":
            cb.qr_url_input_field.value = f"tel:+{cb.phone_prefix.value}{cb.phone_number.value}"
            display_preview_qr(cb.qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)

        elif cb.qr_type_dropdown.value == "SMS":
            cb.qr_url_input_field.value = f"SMSTO:{cb.sms_number.value}:{cb.sms_message.value}"
            display_preview_qr(cb.qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)

        elif cb.qr_type_dropdown.value == "Location":
            cb.qr_url_input_field.value = f"geo:{cb.location_lat.value},{cb.location_lng.value}"
            display_preview_qr(cb.qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)

        elif cb.qr_type_dropdown.value == "Event":
            if cb.date_picker.start_value and cb.date_picker.end_value and cb.start_time_picker.value and cb.end_time_picker.value:
                start_date = normalize_picker_date(cb.date_picker.start_value)
                end_date = normalize_picker_date(cb.date_picker.end_value)
                dtstart_str = f"{start_date.strftime('%Y%m%d')}T{cb.start_time_picker.value.strftime('%H%M%S')}"
                dtend_str = f"{end_date.strftime('%Y%m%d')}T{cb.end_time_picker.value.strftime('%H%M%S')}"
                cb.qr_url_input_field.value = (
                    f"BEGIN:VCALENDAR\r\n"
                    f"VERSION:2.0\r\n"
                    f"BEGIN:VEVENT\r\n"
                    f"SUMMARY:{cb.event_title.value}\r\n"
                    f"LOCATION:{cb.event_location.value}\r\n"
                    f"DTSTART:{dtstart_str}\r\n"
                    f"DTEND:{dtend_str}\r\n"
                    f"END:VEVENT\r\n"
                    f"END:VCALENDAR"
                )
                display_preview_qr(cb.qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)
            else:
                cb.qr_url_input_field.value = (
                    f"BEGIN:VCALENDAR\r\n"
                    f"VERSION:2.0\r\n"
                    f"BEGIN:VEVENT\r\n"
                    f"SUMMARY:{cb.event_title.value}\r\n"
                    f"LOCATION:{cb.event_location.value}\r\n"
                    f"END:VEVENT\r\n"
                    f"END:VCALENDAR"
                )
                display_preview_qr(cb.qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)
        else:
            display_preview_qr(cb.qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)

    def type_trigger(e):
        cb = create_bs_ref["instance"]
        selected = e.control.value 
        cb.qr_url_input_field.value=""
        #Hide everything
        for area in [
            cb.wifi_area, cb.input_row, cb.url_protocol_dropdown, cb.email_general_content, cb.email_adv_content,
            cb.phone_general_content, cb.sms_general_content, cb.location_general_content,
            cb.event_general_content, cb.date_picker_button]:            
            area.visible = False
        #Empty everything
        for field in [
            cb.wifi_name, cb.wifi_password, cb.email_address, cb.email_subject, cb.email_body,
            cb.phone_prefix, cb.phone_number, cb.sms_prefix, cb.sms_number, cb.sms_message,
            cb.location_lat, cb.location_lng, cb.event_title, cb.event_location, cb.start_time_picker, cb.end_time_picker]:
        
            field.value = ""    
        if selected == "WIFI":
            cb.wifi_area.visible=True
        elif selected == "URL/Link":
            cb.input_row.visible=True 
            cb.url_protocol_dropdown.visible = True
            cb.qr_url_input_field.hint_text = "Enter URL here"
            cb.qr_url_input_field.label = "Enter URL"
        elif selected == "Text":
            cb.input_row.visible=True 
            cb.qr_url_input_field.hint_text = "Enter text here"
            cb.qr_url_input_field.label = "Enter text"
        elif selected == "Email":
            cb.email_general_content.visible=True 
        elif selected == "Phone":
            cb.phone_general_content.visible=True 
        elif selected == "SMS":
            cb.sms_general_content.visible=True
        elif selected == "Location":
            cb.location_general_content.visible=True
        elif selected == "Event":
            cb.event_general_content.visible=True
            cb.date_picker_button.visible = True
        prop_changed()
        page.update()

    def get_content():
        cb = create_bs_ref["instance"]
        wifi_subcontainer.visible=False
        wifi_pass_display.visible=False
        extra_vis.visible=False
        email_advanced_container.visible=False
        longitude_container.visible=False
        sms_container.visible=False
        event_summary_container.visible=False
        if cb.qr_type_dropdown.value == "WIFI":
            wifi_subcontainer.visible=True
            text_content.value=cb.wifi_name.value
            text_label.value= "Name"
            wifi_protocol.value = cb.wifi_protocol_dropdown.value
            if wifi_protocol.value != "No password":
                wifi_pass.value = cb.wifi_password.value
                wifi_pass_display.visible=True
            
        elif cb.qr_type_dropdown.value == "URL/Link":
            text_content.value= f"{cb.url_protocol_dropdown.value}{cb.qr_url_input_field.value}"
            text_label.value = "Link"

        elif cb.qr_type_dropdown.value == "Email":
            text_content.value= f"{cb.email_address.value}"
            text_label.value = "Address"
            if cb.email_adv_checkbox.value:
                email_subject_summary.value = cb.email_subject.value
                email_body_summary.value = cb.email_body.value
                email_advanced_container.visible=True
                extra_vis.visible=True
        elif cb.qr_type_dropdown.value == "Phone":
            text_content.value= f"+{cb.phone_prefix.value} {cb.phone_number.value}"
            text_label.value= "Number"

        elif cb.qr_type_dropdown.value == "SMS":
            text_content.value= f"+{cb.sms_prefix.value} {cb.sms_number.value}"
            text_label.value = "Receiver"
            sms_msg.value = cb.sms_message.value
            sms_container.visible=True
            extra_vis.visible=True
            
        elif cb.qr_type_dropdown.value == "Location":
            text_label.value = "Latitude"
            text_content.value= f"{cb.location_lat.value}"
            longitude.value = cb.location_lng.value
            longitude_container.visible=True

        elif cb.qr_type_dropdown.value == "Event":
            text_label.value = "Event"
            text_content.value = cb.event_title.value
            event_title_summary.value = cb.event_title.value
            event_location_summary.value = cb.event_location.value
            event_start_summary.value = cb.start_time_picker.value
            event_end_summary.value = cb.end_time_picker.value
            extra_vis.visible=True
            event_summary_container.visible=True

        elif cb.qr_type_dropdown.value == "Text":
            text_content.value=cb.qr_url_input_field.value
            text_label.value = "Text"

        error_correction_content.value = cb.error_correction_dropdown.value


    create_button = ft.Button(
        icon=ft.Icon(icon=ft.Icons.ADD_ROUNDED, size=24), 
        content=ft.Text(value="Generate a new QR code",size=24),
        on_click=lambda e: qr_creator_open(),
        align=ft.Alignment.CENTER,
        height=70,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=20)
        )
    )

    download_button = ft.Button(
        icon=ft.Icon(icon=ft.Icons.DOWNLOAD_ROUNDED, size=20), 
        align=ft.Alignment.CENTER,
        content=ft.Text(value="Download",size=20),
        on_click=lambda e: show_download_confirm_dialog(),
        height=40,
        margin=ft.Margin(right=5),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),
            color=ft.Colors.SURFACE_CONTAINER_LOW,
            bgcolor=ft.Colors.PRIMARY,
            overlay_color=ft.Colors.ON_PRIMARY_CONTAINER
        )
    )

    modify_text = ft.Text(value="Modify settings",align=ft.Alignment.CENTER,size=20,color=ft.Colors.WHITE)
    clear_text = ft.Text(value="Clear",size=20,color=ft.Colors.RED_400)
    type_icon = ft.Icon(icon=ft.Icons.WIFI_ROUNDED,size=35)

    error_correction_content = ft.Text(value="",size=20,color=ft.Colors.PRIMARY)
    error_correction_container=ft.Column(controls=[
        ft.Text(value="Correction",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
        ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER , content=error_correction_content),
    ])

    text_content = ft.Text(value="",size=20,color=ft.Colors.PRIMARY)
    text_label = ft.Text(value="",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE))

    wifi_protocol = ft.Text(value="",size=20)
    wifi_pass = ft.Text(value="",size=20)
    wifi_pass_display = ft.Column(controls=[
        ft.Text(value="Password",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
        ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=wifi_pass),
    ])

    wifi_subcontainer = ft.Row(visible=False,controls=[       
        ft.Column(controls=[
            ft.Text(value="Security",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
                ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=ft.Row(controls=[
                    ft.Icon(icon=ft.Icons.SHIELD_ROUNDED),
                    wifi_protocol      
                ])),
        ]),
        wifi_pass_display,
    ])      

    def get_content_container(label,content):
        content_container=ft.Column(controls=[
            label,
            ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=content),
        ])
        return content_container

    preview_qr_on_summary = ft.Container()

    filename_textfield = ft.TextField(
        expand=False,
        label="Enter filename",
        hint_text="QR name here",
        border_width=0,
    )

    email_subject_summary =ft.Text(value="",align=ft.Alignment.CENTER,size=20,color=ft.Colors.WHITE)
    email_body_summary =ft.Text(value="",align=ft.Alignment.CENTER,size=20,color=ft.Colors.WHITE)

    email_advanced_container = ft.Column(tight=True,controls=[
        #get_content_container("subject",Text(value=email_subject.value,size=20,color=Colors.PRIMARY)),
        ft.Column(controls=[
            ft.Text(value="Subject",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
            ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=email_subject_summary),
        ]),
        ft.Column(controls=[
            ft.Text(value="Body",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
            ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=email_body_summary),
        ])
    ])

    longitude=ft.Text(value="",size=20,color=ft.Colors.PRIMARY)

    longitude_container = ft.Column(controls=[
        ft.Text(value="Longitude",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
        ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=longitude),
    ])

    sms_msg = ft.Text(value="",size=20,color=ft.Colors.PRIMARY)

    sms_container = ft.Column(visible=False,controls=[
        ft.Text(value="Message",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
        ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=sms_msg),
    ])

    event_title_summary = ft.Text(value="",size=20,color=ft.Colors.PRIMARY)
    event_location_summary = ft.Text(value="",size=20,color=ft.Colors.PRIMARY)
    event_start_summary = ft.Text(value="",size=20,color=ft.Colors.PRIMARY)
    event_end_summary = ft.Text(value="",size=20,color=ft.Colors.PRIMARY)
    
    event_summary_container = ft.Column(visible=False, controls=[
        ft.Column(controls=[
            ft.Text(value="Location",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
            ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=event_location_summary),
        ]),
        ft.Column(controls=[
            ft.Text(value="Start",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
            ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=event_start_summary),
        ]),
        ft.Column(controls=[
            ft.Text(value="End",size=15,margin=ft.Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
            ft.Container(border_radius=10,padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER, content=event_end_summary),
        ]),
    ])

    extra_vis= ft.Container(
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
        border_radius=20,
        padding=10,
        visible=False,
        expand=False,
        align=ft.Alignment.CENTER,
        content=ft.Row(tight=True,scroll=ft.ScrollMode.ADAPTIVE,controls=[
            email_advanced_container,
            sms_container,
            event_summary_container,
            #get_qr_content()
        ])
    )

    summary_visual = ft.Column(tight=True,controls=[
        ft.Container(padding=20,border_radius=30,align=ft.Alignment.CENTER,bgcolor=ft.Colors.INVERSE_PRIMARY,content=preview_qr_on_summary),
        ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            border_radius=20,
            padding=5,
            expand=False,
            width=500,
            align=ft.Alignment.CENTER,
            content=ft.ResponsiveRow(
                spacing=5,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        content=filename_textfield,
                        col={"xs": 12, "sm": 7.7},
                    ),
                    ft.Container(
                        content=download_button,
                        col={"xs": 12, "sm": 4.2},
                    ),
                ],
            ),
        ),
        ft.Row(alignment=ft.MainAxisAlignment.CENTER,margin=ft.Margin(top=40),controls=[
            ft.Container(on_hover=lambda e: handle_modify_hover(e, modify_text,ft.Colors.WHITE,ft.Colors.WHITE),on_click=lambda e:qr_creator_open(),content=modify_text),
            ft.Container(height=20,width=2,bgcolor="grey",margin=ft.Margin(left=5,right=5),content=ft.Text("")),
            ft.Container(on_hover=lambda e: handle_modify_hover(e, clear_text,ft.Colors.RED_200,ft.Colors.RED_400),on_click=lambda e:clear_summary(),content=clear_text),
        ]),
        ft.Container(
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=30,
            padding=10,
            expand=False,
            width=500,
            align=ft.Alignment.CENTER,
            content=ft.Row(tight=True,scroll=ft.ScrollMode.ADAPTIVE,controls=[
                ft.Container(padding=15,border_radius=20,border=ft.Border.all(width=4,color=ft.Colors.PRIMARY),bgcolor=ft.Colors.PRIMARY_CONTAINER,content=type_icon),
                error_correction_container,
                get_content_container(text_label,text_content),
                wifi_subcontainer,
                longitude_container,
                
            ])
        ),
        extra_vis,
    ])

    def handle_modify_hover(e,element,color=ft.Colors.WHITE,default_color=ft.Colors.PRIMARY):
        if e.data == True:
            element.color = color
            element.style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE,decoration_color=color)
        else:
            element.color = default_color
            element.style = None


    bmac_button_top_bar = ft.Button(
        icon=ft.Icons.COFFEE_ROUNDED,
        content="Buy me a coffee",
        visible=True,
        color="yellow",
        #bgcolor=ft.Colors.YELLOW_900,
        icon_color="yellow",
        #on_click=lambda e:asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR","BLANK"))
    )

    top_bar = ft.Row(controls=[
        ft.Row(controls=[
            ft.Text(value="QuickeR",size=24,font_family="MaterialRoundedBold",margin=ft.Margin(left=10)),
        ]),
        ft.Container(
            border_radius=10,
            bgcolor=ft.Colors.TERTIARY_CONTAINER,
            content=ft.Text(
                value="Web",
                size=11,
                font_family="MaterialRoundedBold",
                color=ft.Colors.WHITE,
                style=ft.TextStyle(weight=ft.FontWeight.BOLD)
            ),
            border=ft.Border.all(width=3,color=ft.Colors.TERTIARY),
            padding=7
        ),
        ft.Container(expand=True),
        ft.Row(
            alignment=ft.MainAxisAlignment.END,
            controls=[
                #appearance_setting,
                bmac_button_top_bar,
                ft.IconButton(
                    icon=get_github_icon_by_mode(),
                    on_click=lambda e:asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web","BLANK"))
                ),
                ft.Button(
                    icon=ft.Icons.INFO_OUTLINE_ROUNDED,
                    content="About",
                    on_click=lambda e: open_about_bs()
                ),
            ],
        )
    ])

    overview = ft.Column(
        scroll=ft.ScrollMode.ADAPTIVE,
        alignment=ft.MainAxisAlignment.CENTER,
        #align=ft.CrossAxisAlignment.CENTER,
        expand=True,
        controls=[create_button],
    )

    async def open_url(url_to_open,target: ft.UrlTarget):
        url = url_to_open
        await ft.UrlLauncher().launch_url(ft.Url(url=url, target=target))

    safearea = ft.SafeArea(
        content=ft.Column(
            expand=True,
            controls=[top_bar,overview]
        ),
        expand=True
    )
    page.add(safearea)

    #Updates the app on resize
    def resize_handler():
        if page.width < 600:
            bmac_button_top_bar.visible = False
        else:
            bmac_button_top_bar.visible = True
    resize_handler()

    #Initial exec functions
    page.on_resize = resize_handler

#Run the app
ft.run(main, assets_dir="program_variants/assets")