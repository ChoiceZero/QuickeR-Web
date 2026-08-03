import os
import qrcode
import flet as ft
from flet import (
    DateRangePicker, TimePicker,ExpansionTile,Dropdown,DropdownOption,ThemeMode,Theme,Page,RoundedRectangleBorder,
    ButtonStyle,Divider,BottomSheet,Border,Margin,Icon,Icons, IconButton, Container, Image, TextField, Text, Row, 
    Column, Colors, ScrollMode, AlertDialog, FilePicker, TextButton, Alignment, Button, IconButton, TextStyle, FontWeight,
    RoundedRectangleBorder, BorderSide, MainAxisAlignment, CrossAxisAlignment, Switch
)
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

def add_logo_aligned_to_grid(pil_img, logo_path, qr_obj, max_module_ratio=0.25, bg_color=(255, 255, 255, 255)):
    box_size = qr_obj.box_size
    border = qr_obj.border
    modules_count = len(qr_obj.get_matrix())

    max_logo_modules = int(modules_count * max_module_ratio)
    if max_logo_modules % 2 == 0:
        max_logo_modules -= 1
    max_logo_modules = max(max_logo_modules, 1)

    logo_size_px = max_logo_modules * box_size

    logo = PIL.Image.open(logo_path).convert("RGBA")
    logo = logo.resize((logo_size_px, logo_size_px))

    qr_w, qr_h = pil_img.size

    # centrado directo en píxeles (evita desalineado por redondeo de módulos)
    pos_x = (qr_w - logo_size_px) // 2
    pos_y = (qr_h - logo_size_px) // 2

    pil_img = pil_img.convert("RGBA")

    # fondo opaco detrás del logo, para que no se vean los módulos del QR
    # a través de zonas transparentes del PNG del logo
    backdrop = PIL.Image.new("RGBA", (logo_size_px, logo_size_px), bg_color)
    pil_img.paste(backdrop, (pos_x, pos_y))

    # ahora el logo encima, usando su propio alfa como máscara
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

class LogoPicker:
    def __init__(self, page):
        self.page = page
        self.file_picker = FilePicker()
        page.services.append(self.file_picker)
        page.update()

    async def pick(self, allowed_extensions=None):
        files = await self.file_picker.pick_files(allowed_extensions=allowed_extensions)
        return files[0].path if files else None
        
def main(page: Page):
    ###PAGE SETTINGS--------------------------------------------------------------
    page.title = "QuickeR"
    
    #some variables
    last_qr_image = {"img": None}
    _debounce_task = {"task": None}
    logo_image_path = {"path": None}
    logo_picker_ref = {"instance": None}
    
    ##THEMING--------------------------------------------------------------
    page.fonts = {
        "MaterialRounded":"/GoogleSansFlex.ttf"
    }
    page.theme_mode = ThemeMode.DARK

    #Picks a random theme color and a font
    def theme_selector():
        theme_colors = [
            Colors.BLUE_600,
            Colors.GREEN_600,
            Colors.YELLOW_600,
            Colors.ORANGE_600,
            Colors.RED_600,
            Colors.PURPLE_600,
            Colors.PINK_600,
            Colors.GREY_600
            #Colors.GREY_100
        ]
        selected_theme = theme_colors[random.randint(0,(len(theme_colors)-1))]
        page.theme = Theme(color_scheme_seed=selected_theme, font_family="MaterialRounded")
        page.update()
    theme_selector()

    #Swaps theme mode between light and dark
    def appearance_swapper():
        if page.theme_mode == ThemeMode.DARK:
            page.theme_mode = ThemeMode.LIGHT
        else:
            page.theme_mode = ThemeMode.DARK
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
        preview_qr_area.controls.clear()

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
        preview_qr = Image(src=uri_base64, width=200, height=200, border_radius=10)
        preview_qr_on_summary.content = preview_qr
        preview_qr_area.controls.append(preview_qr)
        page.update()
    file_saver = FilePicker()
    page.services.append(file_saver)
    page.update()

    #Shows a dialog confirming the download and starts the download process, besides offering retries
    def show_download_confirm_dialog():
        if not filename_textfield.value:
            page.show_dialog(AlertDialog(
                title=Text("Missing filename"),
                content=Text("Please enter a filename for the QR code."),
                actions=[TextButton("OK", on_click=lambda e: page.pop_dialog())],
                actions_alignment="end",
            ))
        else:
            page.show_dialog(AlertDialog(
                title=Text("Download started!"),
                content=Text(f"The qr code should download automatically.\n If it doesn't, please retry with the button below."),
                actions=[
                    TextButton("Retry", on_click=lambda e: asyncio.ensure_future(download_qr())),
                    TextButton("Got it!", on_click=lambda e: page.pop_dialog()),
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
    
    #Opens the QR creation bottom sheet
    def qr_creator_open():
        async def _open():
            if create_layout not in page.overlay:
                page.overlay.append(create_layout)
                page.update()
                await asyncio.sleep(0.05)
            create_layout.open = True
            page.update()
        page.run_task(_open)
    
    #Checks that everything is filled in before transitioning to summary view
    def input_checker():
        def alert_empty():
            page.show_dialog(AlertDialog(
                title=Text("Missing required fields"),
                content=Text("Please fill in all required fields for the selected QR type."),
                actions=[TextButton("OK", on_click=lambda e: page.pop_dialog())],
                actions_alignment="end",
            ))

        if qr_type_dropdown.value == "WIFI":
            if not wifi_name.value:
                alert_empty()
                return False
            if wifi_protocol_dropdown.value != "No password" and not wifi_password.value:
                alert_empty()
                return False
        elif qr_type_dropdown.value == "Email":
            if not email_address.value:
                alert_empty()
                return False
        elif qr_type_dropdown.value == "Phone":
            if not phone_number.value or not phone_prefix.value:
                alert_empty()
                return False
        elif qr_type_dropdown.value == "SMS":
            if not sms_number.value or not sms_prefix.value or not sms_message.value:
                alert_empty()
                return False
        elif qr_type_dropdown.value == "Location":
            if not location_lat.value or not location_lng.value:
                alert_empty()
                return False
        elif qr_type_dropdown.value == "Event":
            if not event_title.value or not event_location.value or not date_picker.start_value or not date_picker.end_value or not start_time_picker.value or not end_time_picker.value:
                alert_empty()
                return False
        else:  
            if not qr_url_input_field.value:
                alert_empty()
                return False
        return True

    #Copies text to the clipboard
    async def copy_text_to_clipboard(text):
        await ft.Clipboard().set(text)
        page.show_dialog(AlertDialog(
            title=Text("Text copied"),
            content=Text("The text has been copied to the clipboard."),
            actions=[TextButton("OK", on_click=lambda e: page.pop_dialog())],
            actions_alignment="end",
        ))

    #Transitions to summary view
    def qr_create_triggered():
        def perform_transition():
            type_icon.icon = get_logo()
            get_content()
            if create_button in overview.controls:
                overview.controls.remove(create_button)
                overview.controls.append(summary_visual)
            clean_create_bs_up()
        if input_checker():
            if check_qr_contrast(qr_color_scheme_primary.color, qr_color_scheme_secondary.color) == 1:
                page.show_dialog(AlertDialog(
                    title=Text("Low contrast"),
                    content=Text("The selected colors have low contrast. This may result in a QR code that is difficult to scan. Do you want to continue?"),
                    actions=[
                        TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                        TextButton("Continue", on_click=lambda e: [page.pop_dialog(), perform_transition()]),
                    ],
                    actions_alignment="end",
                ))
            elif check_qr_contrast(qr_color_scheme_primary.color, qr_color_scheme_secondary.color) == 2:
                page.show_dialog(AlertDialog(
                    title=Text("Moderate contrast"),
                    content=Text("The selected colors have moderate contrast. This may result in a QR code that is difficult to scan. Do you want to continue?"),
                    actions=[
                        TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                        TextButton("Continue", on_click=lambda e: [page.pop_dialog(), perform_transition()]),
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
        path = await logo_picker_ref["instance"].pick(["png", "jpg", "jpeg"])
        if path:
            logo_image_path["path"] = path
            prop_changed()

    #Removes the logo from the QR code and updates the preview
    def remove_logo():
        logo_image_path["path"] = None
        prop_changed()

    #Returns the appropriate icon for the selected QR type
    def get_logo():
        if qr_type_dropdown.value == "WIFI":
            return Icons.WIFI_ROUNDED
        elif qr_type_dropdown.value == "URL/Link":
            return Icons.LINK_ROUNDED
        elif qr_type_dropdown.value == "Email":
            return Icons.MAIL_ROUNDED
        elif qr_type_dropdown.value == "Phone":
            return Icons.CALL_ROUNDED
        elif qr_type_dropdown.value == "SMS":
            return Icons.MESSAGE_ROUNDED
        elif qr_type_dropdown.value == "Location":
            return Icons.PIN_ROUNDED
        elif qr_type_dropdown.value == "Event":
            return Icons.PARTY_MODE_ROUNDED
        elif qr_type_dropdown.value == "Text":
            return Icons.TEXT_FORMAT_ROUNDED   

    #Clears the QR creation bottom sheet and resets all input fields
    def clear_dialog():
        delete_dialog = AlertDialog(
            title=Text("Discard?"),
            alignment=Alignment.CENTER,
            actions=[
                Button(content="No", on_click=lambda e: page.pop_dialog()),
                Button(icon=Icons.DELETE,bgcolor=Colors.RED_900,content="Yes", on_click=lambda e: clean_create_bs_up())],
            open=True)
        page.show_dialog(delete_dialog)

    #Clears the summary view and goes back to the home view, resetting all input fields
    def clear_summary():
        def clear_summary_action():
            page.pop_dialog()
            if summary_visual in overview.controls:
                overview.controls.remove(summary_visual)
                overview.controls.append(create_button)
            clean_create_bs_up(full_reset=True)
            page.update()

        page.show_dialog(AlertDialog(
            title=Text("Discard?"),
            alignment=Alignment.CENTER,
            actions=[
                Button(content="No", on_click=lambda e: page.pop_dialog()),
                Button(icon=Icons.DELETE,bgcolor=Colors.RED_900,content="Yes", on_click=lambda e: clear_summary_action())],
            open=True))

    #Clears the QR creation bottom sheet and resets all input fields
    def clean_create_bs_up(full_reset=False):
        if create_layout.open == True:
            create_layout.open = False
        if full_reset:
            for item in [
                wifi_name, wifi_password, qr_url_input_field, email_address, 
                email_subject, email_body, phone_prefix, phone_number, sms_prefix, 
                sms_number, sms_message, location_lat, location_lng, event_title, 
                event_location, start_time_picker, end_time_picker
                ]:
                item.value = ""
        page.update()

    #Opens the about bottom sheet
    def open_about_bs():
        async def _open_about():
            if about_bs not in page.overlay:
                page.overlay.append(about_bs)
                page.update()
                await asyncio.sleep(0.05)
            about_bs.open = True
            page.update()
        page.run_task(_open_about)

    #Closes the about bottom sheet
    def clean_about_bs_up():
        if about_bs.open == True:
            about_bs.open = False
        page.update()   

    #Sets the GitHub icon color based on the current theme mode and whether it should be inverted
    def get_github_icon_by_mode(invert=False):
        if invert:
            if page.theme_mode == ThemeMode.DARK:
                return Image("github-white-icon.webp",color="black",width=20,height=20)
            else:
                return Image("github-white-icon.webp",color="white",width=20,height=20)
        else:
            if page.theme_mode == ThemeMode.DARK:
                return Image("github-white-icon.webp",color="white",width=20,height=20)
            else:
                return Image("github-white-icon.webp",color="black",width=20,height=20)

    ###LAYOUTS AND CONTROLS--------------------------------------------------------------

    #appearance_setting = IconButton(icon=Icons.BRIGHTNESS_6_ROUNDED,on_click=lambda e: appearance_swapper()) -> unused

    ##MAIN LAYOUT --------------------------------------------------------------


    ##ABOUT BOTTOM SHEET --------------------------------------------------------------
    about_bs = BottomSheet(
        draggable=True,
        use_safe_area=True,
        scrollable=True,
        fullscreen=True,
        show_drag_handle=True,
        open=False,
        on_dismiss=lambda e: clean_about_bs_up(),
        content=
            Column(
                horizontal_alignment="center",
                scroll=ScrollMode.AUTO,
                visible=True,
                controls=[
                    Container(
                        content=Column(controls=[
                            Row(alignment="center",controls=[
                                Text(value="QuickeR", size=40, align=Alignment.CENTER, color=Colors.WHITE, style=TextStyle(weight=FontWeight.BOLD)),
                                Container(border_radius=10,bgcolor=Colors.TERTIARY_CONTAINER,content=Text(value="Web", size=15, color=Colors.WHITE, style=TextStyle(weight=FontWeight.BOLD)),margin=Margin.only(left=5),border=Border.all(width=3,color=Colors.TERTIARY),padding=10)
                            ]),
                            Text(value="Quick | Simple | Private | Open Source", size=15, align=Alignment.CENTER, color=Colors.GREY_400, style=TextStyle(weight=FontWeight.W_200))
                        ]),
                        padding=20,
                        bgcolor=Colors.SECONDARY_CONTAINER,
                        border_radius=30,
                        width=page.width,
                        margin=Margin.only(left=20, right=20, bottom=5)
                    ),
                    ExpansionTile(
                        bgcolor=Colors.SURFACE_CONTAINER_HIGH,
                        collapsed_bgcolor=Colors.SURFACE_CONTAINER_HIGH,
                        margin=Margin.only(left=20, right=20, bottom=5),
                        shape=RoundedRectangleBorder(side=BorderSide(width=0), radius=20),
                        collapsed_shape=RoundedRectangleBorder(side=BorderSide(width=0), radius=20),
                        title=Text(value="Support QuickeR", size=15, color=Colors.WHITE,style=TextStyle(weight=FontWeight.BOLD)),
                        controls=[Column(controls=[
                            Container(
                                margin=Margin.only(left=10,right=10),
                                border_radius=20,
                                bgcolor=Colors.SECONDARY_CONTAINER,
                                padding=20,
                                content=Column(
                                    controls=[
                                        Row(controls=[
                                            Icon(icon=Icons.PAYMENT_ROUNDED,color=Colors.WHITE),
                                            Text(value="Donate", size=25, color=Colors.WHITE,style=TextStyle(weight=FontWeight.BOLD)),
                                            Container(content=Text(value="ONE TIME", size=10, color=Colors.WHITE,style=TextStyle(weight=FontWeight.BOLD)),margin=Margin.only(left=5),bgcolor=Colors.TERTIARY_CONTAINER,border=Border.all(width=3, color=Colors.TERTIARY), border_radius=10, padding=5),
                                        ]),
                                        Text(value="If you want to support the project, you can do so by donating via Buy Me a Coffee or GitHub Sponsors.", size=15, color=Colors.WHITE),
                                        Row(alignment=MainAxisAlignment.CENTER,controls=[
                                            Button(
                                                margin=Margin.only(top=10),
                                                content=Text(value="Buy Me a Coffee"),
                                                icon=Icons.COFFEE_ROUNDED, 
                                                #on_click=lambda e: asyncio.ensure_future(open_url("https://www.buymeacoffee.com/ChoiceZero","BLANK")),
                                                style=ButtonStyle(
                                                    shape=RoundedRectangleBorder(radius=12),
                                                    padding=10,
                                                    bgcolor=Colors.PRIMARY,
                                                    color=Colors.SURFACE,
                                                    overlay_color=Colors.ON_PRIMARY_CONTAINER
                                                ),
                                            ),
                                            Button(
                                                margin=Margin.only(top=10),
                                                content=Text(value="GitHub Sponsors"),
                                                icon=ft.CupertinoIcons.HEART_FILL, 
                                                #on_click=lambda e: asyncio.ensure_future(open_url("https://www.buymeacoffee.com/ChoiceZero","BLANK")),
                                                style=ButtonStyle(
                                                    shape=RoundedRectangleBorder(radius=12),
                                                    padding=10,
                                                    bgcolor=Colors.PRIMARY,
                                                    color=Colors.SURFACE,
                                                    overlay_color=Colors.ON_PRIMARY_CONTAINER
                                                ),
                                            )
                                        ])
                                    ]
                                )
                            ),
                            Container(
                                border_radius=20,
                                margin=Margin.only(left=10,right=10),
                                bgcolor=Colors.SECONDARY_CONTAINER,
                                padding=20,
                                content=Column(
                                    controls=[
                                        Row(controls=[
                                            Icon(icon=Icons.CODE_ROUNDED,color=Colors.WHITE),
                                            Text(value="Contribute", size=25, color=Colors.WHITE,style=TextStyle(weight=FontWeight.BOLD)),
                                        ]),
                                        Text(value="Contribute code or report bugs in order to improve the project as a community effort.", size=15, color=Colors.WHITE),
                                        Row(alignment=MainAxisAlignment.CENTER,controls=[
                                            Button(
                                                align=Alignment.CENTER,
                                                margin=Margin.only(top=10),
                                                content=Text(value="QuickeR-Web"),
                                                icon=get_github_icon_by_mode(True), 
                                                on_click=lambda e: asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web","BLANK")),
                                                style=ButtonStyle(
                                                    shape=RoundedRectangleBorder(radius=12),
                                                    padding=10,
                                                    bgcolor=Colors.PRIMARY,
                                                    color=Colors.SURFACE,
                                                    overlay_color=Colors.ON_PRIMARY_CONTAINER
                                                ),
                                            ),
                                            Button(
                                                content=Text(value="Report a bug"),
                                                icon=Icons.BUG_REPORT_ROUNDED,
                                                margin=Margin.only(top=10),
                                                on_click=lambda e: asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web/issues","BLANK")),
                                                style=ButtonStyle(
                                                    shape=RoundedRectangleBorder(radius=12),
                                                    padding=10,
                                                    bgcolor=Colors.PRIMARY,
                                                    color=Colors.SURFACE,
                                                    overlay_color=Colors.ON_PRIMARY_CONTAINER
                                                ),
                                            )
                                        ])   
                                    ]
                                )
                            ),
                            Container(
                                border_radius=20,
                                margin=Margin.only(left=10,right=10,bottom=10),
                                bgcolor=Colors.SECONDARY_CONTAINER,
                                padding=20,
                                content=Column(
                                    controls=[
                                        Row(controls=[
                                            Icon(icon=Icons.SHARE_ROUNDED,color=Colors.WHITE),
                                            Text(value="Share the app", size=25, color=Colors.WHITE,style=TextStyle(weight=FontWeight.BOLD)),
                                        ]),
                                        Text(value="Help spread the word about the app and recommend it to others. The more users, the more interest in the project!", size=15, color=Colors.WHITE),
                                        Button(
                                            align=Alignment.CENTER,
                                            content=Text(value="Copy link to clipboard"),
                                            icon=Icons.COPY_ALL_ROUNDED,
                                            margin=Margin.only(top=10),
                                            on_click=lambda e: asyncio.ensure_future(copy_text_to_clipboard("https://choicezero.github.io/QuickeR-Web/")),
                                            style=ButtonStyle(
                                                shape=RoundedRectangleBorder(radius=12),
                                                padding=10,
                                                bgcolor=Colors.PRIMARY,
                                                color=Colors.SURFACE,
                                                overlay_color=Colors.ON_PRIMARY_CONTAINER
                                            ),
                                        )
                                    ]
                                )
                            ),
                        ])]
                    ),
                    Text(value="General information", size=17, color=Colors.WHITE, margin=Margin.only(left=20, right=20, top=15)),
                    Container(
                        width=page.width,
                        border_radius=20,
                        padding=20,
                        margin=Margin.only(left=20, right=20, bottom=5),
                        bgcolor=Colors.SURFACE_CONTAINER_HIGH,
                        content=Column(controls=[
                            Row(controls=[
                                Icon(icon=Icons.NUMBERS_ROUNDED, size=15, color=Colors.PRIMARY),
                                Text(value=("Version"), size=15, color=Colors.GREY_400),
                                Container(expand=True),
                                Text(value=APP_VERSION, size=15, color=Colors.PRIMARY)
                            ]),
                            Divider(color=Colors.SURFACE_CONTAINER_LOW,thickness=2),
                            Row(controls=[
                                Icon(icon=Icons.LIBRARY_BOOKS_ROUNDED, size=15, color=Colors.PRIMARY),
                                Text(value=("License"), size=15, color=Colors.GREY_400),
                                Container(expand=True),
                                Text(value="MIT License", size=15, color=Colors.PRIMARY)
                            ]), 
                            Divider(color=Colors.SURFACE_CONTAINER_LOW,thickness=2),
                            Row(controls=[
                                Icon(icon=Icons.PERSON_2_ROUNDED, size=15, color=Colors.PRIMARY),
                                Text(value=("Developed by"), size=15, color=Colors.GREY_400),
                                Container(expand=True),
                                Text(value="Unax Martinez Llorente (aka ChoiceZero).", size=15, color=Colors.WHITE)
                            ]),
                        ])
                    ),
                    Text(value="Links", size=17, color=Colors.WHITE, margin=Margin.only(left=20, right=20, top=15)),
                    Container(
                        width=page.width,
                        border_radius=20,
                        padding=20,
                        margin=Margin.only(left=20, right=20, bottom=5),
                        bgcolor=Colors.SURFACE_CONTAINER_HIGH,
                        content=Column(controls=[
                            Row(controls=[
                                Icon(icon=Icons.INSERT_LINK_ROUNDED, size=15, color=Colors.PRIMARY),
                                Text(value=("Repository"), size=15, color=Colors.GREY_400),
                                Container(expand=True),
                                Button(
                                    content=Text(value="QuickeR-Web"),
                                    icon=get_github_icon_by_mode(True), 
                                    on_click=lambda e: asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web","BLANK")),
                                    style=ButtonStyle(
                                        shape=RoundedRectangleBorder(radius=12),
                                        padding=10,
                                        bgcolor=Colors.PRIMARY,
                                        color=Colors.SURFACE,
                                        overlay_color=Colors.ON_PRIMARY_CONTAINER
                                    ),
                                )
                            ]),
                            Divider(color=Colors.SURFACE_CONTAINER_LOW,thickness=2),
                            Row(controls=[
                                Icon(icon=Icons.INSERT_LINK_ROUNDED, size=15, color=Colors.PRIMARY),
                                Text(value=("Bugs"), size=15, color=Colors.GREY_400),
                                Container(expand=True),
                                Button(
                                    content=Text(value="Report a bug"),
                                    icon=Icons.BUG_REPORT_ROUNDED,
                                    on_click=lambda e: asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web","BLANK")),
                                    style=ButtonStyle(
                                        shape=RoundedRectangleBorder(radius=12),
                                        padding=10,
                                        bgcolor=Colors.PRIMARY,
                                        color=Colors.SURFACE,
                                        overlay_color=Colors.ON_PRIMARY_CONTAINER
                                    ),
                                )
                            ]),
                            Divider(color=Colors.SURFACE_CONTAINER_LOW,thickness=2),
                            Row(controls=[
                                Icon(icon=Icons.INSERT_LINK_ROUNDED, size=15, color=Colors.PRIMARY),
                                Text(value=("Release notes"), size=15, color=Colors.GREY_400),
                                Container(expand=True),
                                Button(
                                    content=Text(value="Release notes"),
                                    icon=Icons.NEW_RELEASES_ROUNDED,
                                    on_click=lambda e: asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web/releases","BLANK")),
                                    style=ButtonStyle(
                                        shape=RoundedRectangleBorder(radius=12),
                                        padding=10,
                                        bgcolor=Colors.PRIMARY,
                                        color=Colors.SURFACE,
                                        overlay_color=Colors.ON_PRIMARY_CONTAINER
                                    ),
                                )
                            ]),
                        ])
                    ),
                    Text(value="Privacy", size=17, color=Colors.WHITE, margin=Margin.only(left=20, right=20, top=15)),
                    Container(
                        width=page.width,
                        border_radius=20,
                        padding=20,
                        margin=Margin.only(left=20, right=20, bottom=5),
                        bgcolor=Colors.SURFACE_CONTAINER_HIGH,
                        content=Column(controls=[
                            Row(controls=[
                                Icon(icon=Icons.DISABLED_VISIBLE_ROUNDED, size=15, color=Colors.PRIMARY),
                                Text(value=("Private"), size=15, color=Colors.GREY_400),
                                Container(expand=True),
                                Text(value="No telemetry or analytics are used", size=15, color=Colors.WHITE)  
                            ]),
                            Divider(color=Colors.SURFACE_CONTAINER_LOW,thickness=2),
                            Row(controls=[
                                Icon(icon=Icons.EDIT_ROUNDED, size=15, color=Colors.PRIMARY),
                                Text(value=("Open source"), size=15, color=Colors.GREY_400),
                                Container(expand=True),
                                Text(value="Fully open source and auditable", size=15, color=Colors.WHITE)  
                            ]),
                            Divider(color=Colors.SURFACE_CONTAINER_LOW,thickness=2),
                            Row(controls=[
                                Icon(icon=Icons.VERIFIED_USER_ROUNDED, size=15, color=Colors.PRIMARY),
                                Text(value=("Personal"), size=15, color=Colors.GREY_400),
                                Container(expand=True),
                                Text(value="No private data is collected or stored", size=15, color=Colors.WHITE)
                            ]),
                        ])
                    ),
                    Row(alignment=MainAxisAlignment.CENTER,controls=[Text(value="Made with ❤️ in Spain.", size=15, color=Colors.GREY_400)]),
                    Text(value="© 2026 Unax Martinez Llorente.", size=15, color=Colors.GREY_400),
                    Container(width=50),    
                ]
            )
        )   
    page.overlay.append(about_bs)

    ##CREATE BOTTOM SHEET --------------------------------------------------------------
    qr_type_dropdown = Dropdown(on_select=lambda e: type_trigger(e),border_width=0,value="URL/Link",options=[
        DropdownOption(text="URL/Link",leading_icon=Icons.LINK_ROUNDED),
        DropdownOption(text="Text",leading_icon=Icons.TEXT_FIELDS_ROUNDED),
        DropdownOption(text="WIFI",leading_icon=Icons.WIFI_ROUNDED),
        DropdownOption(text="Email",leading_icon=Icons.MAIL_OUTLINE_ROUNDED),
        DropdownOption(text="Phone",leading_icon=Icons.PHONE_ANDROID_ROUNDED),
        DropdownOption(text="Location",leading_icon=Icons.PIN_DROP_ROUNDED),
        DropdownOption(text="SMS",leading_icon=Icons.MESSAGE_ROUNDED),
        DropdownOption(text="Event",leading_icon=Icons.STAR_BORDER_ROUNDED),
    ])

    #URL
    url_protocol_dropdown = Dropdown(value="https://",border_width=0,options=[
        DropdownOption(text="https://"),
        DropdownOption(text="http://"),
        ])

    #WIFI
    wifi_name= TextField(
        expand=True,
        border_width=0,
        label="Enter network name",
        on_change=lambda e: prop_changed()
    )

    wifi_protocol_dropdown = Dropdown(value="WPA2",border_width=0,on_select=lambda e: wifi_protocol_changed(e),options=[
        DropdownOption(text="WPA2"),
        DropdownOption(text="WPA"),
        DropdownOption(text="WEP"),
        DropdownOption(text="No password"),
    ])

    def wifi_protocol_changed(e):
        selected = e.control.value 
        if selected == "No password":
            wifi_password_setting.visible = False
        else:
            wifi_password_setting.visible = True
        prop_changed()
    
    wifi_password= TextField(
        expand=True,
        border_width=0,
        label="Enter network password",
        on_change=lambda e: prop_changed()
    )

    wifi_password_setting= Column(visible=True,controls=[
        Divider(color="grey"),
        Row(controls=[
            Icon(icon=Icons.PASSWORD_ROUNDED),
            Text(value=("WIFI password"), size=20),
            Container(expand=True),
        ]),
        Container(border_radius=10,bgcolor=Colors.SURFACE_CONTAINER,content=wifi_password),
    ])

    wifi_area = Column(visible=False,controls=[
        Row(controls=[
            Icon(icon=Icons.TEXT_FIELDS_ROUNDED),
            Text(value=("Network name"), size=20),
            Container(expand=True)
        ]),
        Container(border_radius=10,
            bgcolor=Colors.SURFACE_CONTAINER,
            content=wifi_name
        ),
        Divider(color="grey"),
        Container(
            content=Row(controls=[
                Icon(icon=Icons.INFO_OUTLINE_ROUNDED,color=Colors.WHITE),
                Container(expand=True,content=Text(
                    value="If your network has no password, select it here!",
                    size=16,
                    color=Colors.WHITE
                )),
                ],
            ),
            padding=15,
            bgcolor=Colors.INVERSE_PRIMARY,border_radius=30,
            margin=Margin.only(left=0, right=0, top=5, bottom=5,)
        ),
        Row(controls=[
            Icon(icon=Icons.SHIELD),
            Text(value=("WIFI security protocol"), size=20),
            Container(expand=True),
            Container(border_radius=50,bgcolor=Colors.SURFACE_CONTAINER,content=wifi_protocol_dropdown)
        ]),
        wifi_password_setting
    ])

    # Email
    email_address = TextField(expand=True,border_width=0,label="Enter address",hint_text="Enter address",on_change=lambda e: prop_changed())
    email_adv_checkbox = Switch(value=False, on_change=lambda e: email_checkbox_changed())
    email_general_content=Column(visible=False,controls=[
        Row(controls=[
            Icon(icon=Icons.MAIL_ROUNDED),
            Text(value=("Address"), size=20),
            Container(expand=True)
        ]),
        Container(border_radius=10,
            bgcolor=Colors.SURFACE_CONTAINER,
            content=email_address
        ),
        Divider(color="grey"),
        Row(controls=[
            Icon(icon=Icons.TEXT_FIELDS_ROUNDED),
            Text(value=("Advanced options"), size=20),
            Container(expand=True),
            Container(border_radius=50,bgcolor=Colors.SURFACE_CONTAINER,content=email_adv_checkbox)
        ]),
    ])

    # -> On checkbox changed
    def email_checkbox_changed():
        if email_adv_checkbox.value:
            email_adv_content.visible = True
        else:
            email_adv_content.visible = False
        prop_changed()

    email_subject = TextField(expand=True, border_width=0, label="Subject", on_change=lambda e: prop_changed())
    email_body = TextField(expand=True, border_width=0, label="Body", multiline=True, on_change=lambda e: prop_changed())
    email_adv_content = Column(visible=False, controls=[
        Row(controls=[Icon(icon=Icons.SUBJECT_ROUNDED), Text(value="Subject", size=20), Container(expand=True)]),
        Container(border_radius=10, bgcolor=Colors.SURFACE_CONTAINER, content=email_subject),
        Divider(color="grey"),
        Row(controls=[Icon(icon=Icons.TEXT_FIELDS_ROUNDED), Text(value="Body", size=20), Container(expand=True)]),
        Container(border_radius=10, bgcolor=Colors.SURFACE_CONTAINER, content=email_body),
    ])

    # Phone
    phone_prefix = TextField(
        border_width=0,
        label="",
        hint_text="",
        width=80,
        max_length=4,
        counter=Container(),
        keyboard_type=ft.KeyboardType.NUMBER,
        on_change=lambda e: prop_changed()
    )
    phone_number = TextField(
        expand=True,
        border_width=0,
        label="Enter address",
        hint_text="",
        keyboard_type=ft.KeyboardType.NUMBER,
        on_change=lambda e: prop_changed()
    )   
    phone_general_content=Column(visible=False,controls=[
        Row(controls=[
            Icon(icon=Icons.CALL_ROUNDED),
            Text(value=("Phone number"), size=20),
            Container(expand=True)
        ]),
        Row(
            expand=True,
            controls=[
            Container(
                border_radius=10,
                bgcolor=Colors.SURFACE_CONTAINER,
                content=Row(controls=[
                    Text("+",margin=Margin(left=15),size=15),
                    phone_prefix
                ])
            ),
            Container(
                expand=True,
                border_radius=10,
                bgcolor=Colors.SURFACE_CONTAINER,
                content=phone_number
            ),
        ])
    ]) 

    # SMS
    sms_prefix = TextField(
        border_width=0,
        label="",
        hint_text="",
        width=80,
        max_length=4,
        counter=Container(),
        keyboard_type=ft.KeyboardType.NUMBER,
        on_change=lambda e: prop_changed()
    )
    sms_number = TextField(
        expand=True,
        border_width=0,
        label="Enter phone number",
        keyboard_type=ft.KeyboardType.NUMBER,
        on_change=lambda e: prop_changed()
    )
    sms_message = TextField(expand=True, border_width=0, label="Enter message", multiline=True, on_change=lambda e: prop_changed())

    sms_general_content = Column(visible=False, controls=[
        Row(controls=[Icon(icon=Icons.SMS_ROUNDED), Text(value="Phone number", size=20), Container(expand=True)]),
        Row(controls=[
            Container(
                border_radius=10,
                bgcolor=Colors.SURFACE_CONTAINER,
                content=Row(controls=[Text("+", margin=Margin(left=15), size=15), sms_prefix])
            ),
            Container(border_radius=10, expand=True, bgcolor=Colors.SURFACE_CONTAINER, content=sms_number),
        ]),
        Divider(color="grey"),
        Row(controls=[Icon(icon=Icons.MESSAGE_ROUNDED), Text(value="Message", size=20), Container(expand=True)]),
        Container(border_radius=10, bgcolor=Colors.SURFACE_CONTAINER, content=sms_message),
    ])

    # Location
    location_lat = TextField(expand=True, border_width=0, label="Latitude", keyboard_type=ft.KeyboardType.NUMBER, on_change=lambda e: prop_changed())
    location_lng = TextField(expand=True, border_width=0, label="Longitude", keyboard_type=ft.KeyboardType.NUMBER, on_change=lambda e: prop_changed())

    location_general_content = Column(visible=False, controls=[
        Row(controls=[Icon(icon=Icons.PIN_DROP_ROUNDED), Text(value="Coordinates", size=20), Container(expand=True)]),
        Row(controls=[
            Container(border_radius=10, expand=True, bgcolor=Colors.SURFACE_CONTAINER, content=location_lat),
            Container(border_radius=10, expand=True, bgcolor=Colors.SURFACE_CONTAINER, content=location_lng),
        ]),
    ])

    # Event (vCalendar/iCal)
    event_title = TextField(expand=True, border_width=0, label="Event title", on_change=lambda e: prop_changed())
    event_location = TextField(expand=True, border_width=0, label="Location", on_change=lambda e: prop_changed())

    date_picker = DateRangePicker(open=False, on_change=lambda e: prop_changed())
    start_time_picker = TimePicker(open=False, on_change=lambda e: prop_changed())
    end_time_picker = TimePicker(open=False, on_change=lambda e: prop_changed())
    
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

    date_picker_button = Button(content="Date period",icon=Icons.CALENDAR_MONTH_ROUNDED, on_click=lambda e: open_date_picker(e), style=ButtonStyle(shape=RoundedRectangleBorder(radius=12), bgcolor={"": Colors.SURFACE_CONTAINER}), tooltip="Pick date range")
    start_time_picker_button = Button(content="Start time",icon=Icons.ACCESS_TIME_ROUNDED, on_click=lambda e: open_start_time(e), style=ButtonStyle(shape=RoundedRectangleBorder(radius=12), bgcolor={"": Colors.SURFACE_CONTAINER}), tooltip="Pick start time")
    end_time_picker_button = Button(content="End time",icon=Icons.ACCESS_TIME_ROUNDED, on_click=lambda e: open_end_time(e), style=ButtonStyle(shape=RoundedRectangleBorder(radius=12), bgcolor={"": Colors.SURFACE_CONTAINER}), tooltip="Pick end time")

    event_general_content = Column(visible=False, controls=[
        Row(controls=[Icon(icon=Icons.STAR_BORDER_ROUNDED), Text(value="Event title", size=20), Container(expand=True)]),
        Container(border_radius=10, bgcolor=Colors.SURFACE_CONTAINER, content=event_title),
        Divider(color="grey"),
        Row(controls=[Icon(icon=Icons.PIN_DROP_ROUNDED), Text(value="Location", size=20), Container(expand=True)]),
        Container(border_radius=10, bgcolor=Colors.SURFACE_CONTAINER, content=event_location),
        Divider(color="grey"),
        Row(controls=[Icon(icon=Icons.ACCESS_TIME_ROUNDED), Text(value="Date and time", size=20), Container(expand=True)]),
        Container(
            content=Row(controls=[
                Icon(icon=Icons.INFO_OUTLINE_ROUNDED,color=Colors.WHITE),
                Container(expand=True,content=Text(
                    value="Please change all fields below here!",
                    size=16,
                    color=Colors.WHITE
                )),
                ],
            ),
            padding=15,
            bgcolor=Colors.INVERSE_PRIMARY,border_radius=30,
            margin=Margin.only(left=0, right=0, top=5, bottom=5,)
        ),
        Row(controls=[
            date_picker_button,
            start_time_picker_button,
            end_time_picker_button,
        ]),
    ])
    
    qr_url_input_field = TextField(expand=True,border_width=0,label="Enter URL or text",on_change=lambda e: prop_changed())
    error_correction_dropdown = Dropdown(value="M (15%)",border_width=0,on_select=lambda e: prop_changed(),options=[
        DropdownOption(text="L (7%)"),
        DropdownOption(text="M (15%)"),
        DropdownOption(text="Q (25%)"),
        DropdownOption(text="H (30%)"),
        ])
    qr_color_scheme_primary = MaterialPicker(on_color_change=lambda e:prop_changed(),color="black")
    qr_color_scheme_secondary = MaterialPicker(on_color_change=lambda e:prop_changed(),color="white")

    preview_qr_area= Row(controls=[], alignment=ft.MainAxisAlignment.CENTER,expand=False, tight=True)

    input_row = Column(controls=[Row(controls=[Icon(icon=Icons.SHORT_TEXT_ROUNDED),Text(value=("Content"), size=20)]),Row(visible=True,controls=[Container(border_radius=50,bgcolor=Colors.SURFACE_CONTAINER,content=url_protocol_dropdown),Container(border_radius=10,expand=True,bgcolor=Colors.SURFACE_CONTAINER,content=qr_url_input_field)]),
    ])
    create_layout= BottomSheet(draggable=False,use_safe_area=True,scrollable=False,fullscreen=True,open=False,on_dismiss=lambda e: clean_create_bs_up(),content=
        Column(horizontal_alignment="center",scroll=ScrollMode.AUTO,controls=[
            Container(bgcolor=Colors.INVERSE_PRIMARY,border_radius=30,expand=False,content=preview_qr_area,padding=20,),
            Container(bgcolor=Colors.SECONDARY_CONTAINER,border_radius=30,margin=Margin.only(left=20, right=20, top=5, bottom=5),padding=20,content=
                Row(alignment="center",controls=[
                    IconButton(
                        icon=Icons.CLOSE,
                        expand=True, 
                        on_click=lambda e: clear_dialog(),    
                        style=ButtonStyle(
                            shape=RoundedRectangleBorder(radius=12),
                            bgcolor={"": Colors.RED_500}, 
                        )
                    ),
                    IconButton(
                        icon=Icons.CHECK,
                        expand=True,
                        on_click=lambda e: qr_create_triggered(), 
                        style=ButtonStyle(
                            shape=RoundedRectangleBorder(radius=12),
                            bgcolor={"": Colors.INVERSE_PRIMARY}, 
                        )
                    ),
                ])
            ),
            Container(bgcolor=Colors.SURFACE_CONTAINER_HIGH,border_radius=30,margin=Margin.only(left=20, right=20, top=5, bottom=5),padding=20,content=
                Column(controls=[
                    Row(controls=[Icon(icon=Icons.ARROW_DROP_DOWN_CIRCLE_OUTLINED),Text(value=("QR Type"), size=20),Container(expand=True),Container(border_radius=50,bgcolor=Colors.SURFACE_CONTAINER,content=qr_type_dropdown)]),
                    Divider(color="grey"),
                    wifi_area,
                    input_row,
                    email_general_content,
                    email_adv_content,
                    phone_general_content,
                    sms_general_content,
                    location_general_content,
                    event_general_content,
                    Divider(color="grey"),
                    Row(controls=[Icon(icon=Icons.CHECK_CIRCLE_OUTLINE_ROUNDED),Text(value=("Error correction level"), size=20),Container(expand=True),Container(border_radius=50,bgcolor=Colors.SURFACE_CONTAINER,content=error_correction_dropdown)]), 
                ])
            ),
            Text(value="Customization", size=18,color=Colors.PRIMARY),
            Container(bgcolor=Colors.SURFACE_CONTAINER_HIGH,border_radius=30,margin=Margin.only(left=20, right=20, top=5, bottom=5),padding=20,content=
                Column(controls=[
                    Row(controls=[Icon(icon=Icons.ADD_PHOTO_ALTERNATE_ROUNDED),Text(value=("Logo/Branding"), size=20)]),
                    Container(
                        content=Row(controls=[
                            Icon(icon=Icons.ERROR_OUTLINE_ROUNDED,color=Colors.WHITE),
                            Container(expand=True,content=Text(
                                value="As logos take up a big chunk of the QR's area, scanability may be greatly reduced. Thus, it is highly recommended that H level error correction is used.",
                                size=16,
                                color=Colors.WHITE
                            )),
                            ],
                        ),
                        padding=15,
                        bgcolor=Colors.RED_500,border_radius=30,
                        margin=Margin.only(left=0, right=0, top=5, bottom=5,)
                    ),
                    Row(controls=[
                    Button(content="Pick image from folder",icon=Icons.FOLDER_COPY_ROUNDED, on_click=lambda e: asyncio.ensure_future(pick_logo())),
                    Container(expand=True),
                    Button(content="Remove logo",icon=Icons.DELETE_ROUNDED, on_click=lambda e: remove_logo()),
                    ]),
                    Divider(color="grey"),
                    Text(value=("Color scheme"), size=20, color=Colors.PRIMARY),
                    Container(
                        content=Row(controls=[
                            Icon(icon=Icons.WARNING_AMBER_ROUNDED,color=Colors.WHITE),
                            Container(expand=True,content=Text(
                                value="Due to c based tools not being supported on WASM, color checking is not available. Please be sensible with the colors you choose and ensure that the foreground color is always clearly darker.",
                                size=16,
                                color=Colors.WHITE
                            )),
                            ],
                        ),
                        padding=15,
                        bgcolor=Colors.ORANGE_500,border_radius=30,
                        margin=Margin.only(left=0, right=0, top=5, bottom=5,)
                    ),
                    ExpansionTile(title="Primary color:",controls=qr_color_scheme_primary,shape=ft.RoundedRectangleBorder(side=ft.BorderSide(width=0), radius=20),collapsed_shape=ft.RoundedRectangleBorder(side=ft.BorderSide(width=0), radius=20)),
                    ExpansionTile(title="Background color:",controls=qr_color_scheme_secondary,shape=ft.RoundedRectangleBorder(side=ft.BorderSide(width=0), radius=20),collapsed_shape=ft.RoundedRectangleBorder(side=ft.BorderSide(width=0), radius=20)),
                ])
            ),
            Container(height=50)
        ]),
    )

    def prop_changed():
        if _debounce_task["task"] is not None:
            _debounce_task["task"].cancel()
        _debounce_task["task"] = page.run_task(_debounced_update)

    async def _debounced_update():
        await asyncio.sleep(0.3)
        color_raw_1 = qr_color_scheme_primary.color  
        if color_raw_1 and color_raw_1.startswith("#") and len(color_raw_1) == 9:
            color_rgb_1 = "#" + color_raw_1[3:] 
        else:
            color_rgb_1 = color_raw_1

        color_raw_2 = qr_color_scheme_secondary.color  
        if color_raw_2 and color_raw_2.startswith("#") and len(color_raw_2) == 9:
            color_rgb_2 = "#" + color_raw_2[3:] 
        else:
            color_rgb_2 = color_raw_2

        error_correction = ERROR_CORRECTION_MAP.get(error_correction_dropdown.value, qrcode.constants.ERROR_CORRECT_M)

        if qr_type_dropdown.value == "WIFI":
            if wifi_protocol_dropdown.value != "No password":
                qr_url_input_field.value = f"WIFI:S:{wifi_name.value};T:{wifi_protocol_dropdown.value};P:{wifi_password.value};;"
            else:
                qr_url_input_field.value = f"WIFI:S:{wifi_name.value};T:nopass;;"
            display_preview_qr(qr_url_input_field.value, color_rgb_1, color_rgb_2,error_correction)
        elif qr_type_dropdown.value == "URL/Link":
                if url_protocol_dropdown.value == "https://":
                    create_val = "https://"+qr_url_input_field.value
                else:
                    create_val = "http://"+qr_url_input_field.value
                display_preview_qr(create_val, color_rgb_1, color_rgb_2,error_correction)
        elif qr_type_dropdown.value == "Email":
            if email_adv_checkbox.value:
                params = []
                if email_subject.value:
                    params.append(f"subject={urllib.parse.quote(email_subject.value)}")
                if email_body.value:
                    params.append(f"body={urllib.parse.quote(email_body.value)}")
                query = "&".join(params)
                qr_url_input_field.value = f"mailto:{email_address.value}" + (f"?{query}" if query else "")
            else:
                qr_url_input_field.value = f"mailto:{email_address.value}"
            display_preview_qr(qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)

        elif qr_type_dropdown.value == "Phone":
            qr_url_input_field.value = f"tel:+{phone_prefix.value}{phone_number.value}"
            display_preview_qr(qr_url_input_field.value, color_rgb_1, color_rgb_2,error_correction)

        elif qr_type_dropdown.value == "SMS":
            qr_url_input_field.value = f"SMSTO:{sms_number.value}:{sms_message.value}"
            display_preview_qr(qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)

        elif qr_type_dropdown.value == "Location":
            qr_url_input_field.value = f"geo:{location_lat.value},{location_lng.value}"
            display_preview_qr(qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)

        elif qr_type_dropdown.value == "Event":
            if date_picker.start_value and date_picker.end_value and start_time_picker.value and end_time_picker.value:
                start_date = normalize_picker_date(date_picker.start_value)
                end_date = normalize_picker_date(date_picker.end_value)
                dtstart_str = f"{start_date.strftime('%Y%m%d')}T{start_time_picker.value.strftime('%H%M%S')}"
                dtend_str = f"{end_date.strftime('%Y%m%d')}T{end_time_picker.value.strftime('%H%M%S')}"
                qr_url_input_field.value = (
                    f"BEGIN:VCALENDAR\r\n"
                    f"VERSION:2.0\r\n"
                    f"BEGIN:VEVENT\r\n"
                    f"SUMMARY:{event_title.value}\r\n"
                    f"LOCATION:{event_location.value}\r\n"
                    f"DTSTART:{dtstart_str}\r\n"
                    f"DTEND:{dtend_str}\r\n"
                    f"END:VEVENT\r\n"
                    f"END:VCALENDAR"
                )
                display_preview_qr(qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)
            else:
                qr_url_input_field.value = (
                    f"BEGIN:VCALENDAR\r\n"
                    f"VERSION:2.0\r\n"
                    f"BEGIN:VEVENT\r\n"
                    f"SUMMARY:{event_title.value}\r\n"
                    f"LOCATION:{event_location.value}\r\n"
                    f"END:VEVENT\r\n"
                    f"END:VCALENDAR"
                )
                display_preview_qr(qr_url_input_field.value, color_rgb_1, color_rgb_2, error_correction)
        else:
            display_preview_qr(qr_url_input_field.value, color_rgb_1, color_rgb_2,error_correction)

    def type_trigger(e):
        selected = e.control.value 
        qr_url_input_field.value=""
        #Hide everything
        for area in [
            wifi_area, input_row, url_protocol_dropdown, email_general_content, email_adv_content,
            phone_general_content, sms_general_content, location_general_content,
            event_general_content,date_picker_button]:            
            area.visible = False
        #Empty everything
        for field in [
            wifi_name, wifi_password, email_address, email_subject, email_body,
            phone_prefix, phone_number, sms_prefix, sms_number, sms_message,
            location_lat, location_lng, event_title, event_location, start_time_picker, end_time_picker]:
        
            field.value = ""    
        if selected == "WIFI":
            wifi_area.visible=True
        elif selected == "URL/Link":
            input_row.visible=True 
            url_protocol_dropdown.visible = True
            qr_url_input_field.hint_text = "Enter URL here"
            qr_url_input_field.label = "Enter URL"
        elif selected == "Text":
            input_row.visible=True 
            qr_url_input_field.hint_text = "Enter text here"
            qr_url_input_field.label = "Enter text"
        elif selected == "Email":
            email_general_content.visible=True 
        elif selected == "Phone":
            phone_general_content.visible=True 
        elif selected == "SMS":
            sms_general_content.visible=True
        elif selected == "Location":
            location_general_content.visible=True
        elif selected == "Event":
            event_general_content.visible=True
            date_picker_button.visible = True
        prop_changed()
        page.update()

    def get_content():
        wifi_subcontainer.visible=False
        wifi_pass_display.visible=False
        extra_vis.visible=False
        email_advanced_container.visible=False
        longitude_container.visible=False
        sms_container.visible=False
        event_summary_container.visible=False
        if qr_type_dropdown.value == "WIFI":
            wifi_subcontainer.visible=True
            text_content.value=wifi_name.value
            text_label.value= "Name"
            wifi_protocol.value = wifi_protocol_dropdown.value
            if wifi_protocol.value != "No password":
                wifi_pass.value = wifi_password.value
                wifi_pass_display.visible=True
            
        elif qr_type_dropdown.value == "URL/Link":
            text_content.value= f"{url_protocol_dropdown.value}{qr_url_input_field.value}"
            text_label.value = "Link"

        elif qr_type_dropdown.value == "Email":
            text_content.value= f"{email_address.value}"
            text_label.value = "Address"
            if email_adv_checkbox.value:
                email_subject_summary.value =email_subject.value
                email_body_summary.value =email_body.value
                email_advanced_container.visible=True
                extra_vis.visible=True
        elif qr_type_dropdown.value == "Phone":
            text_content.value= f"+{phone_prefix.value} {phone_number.value}"
            text_label.value= "Number"

        elif qr_type_dropdown.value == "SMS":
            text_content.value= f"+{sms_prefix.value} {sms_number.value}"
            text_label.value = "Receiver"
            sms_msg.value = sms_message.value
            sms_container.visible=True
            extra_vis.visible=True
            
        elif qr_type_dropdown.value == "Location":
            text_label.value = "Latitude"
            text_content.value= f"{location_lat.value}"
            longitude.value = location_lng.value
            longitude_container.visible=True

        elif qr_type_dropdown.value == "Event":
            text_label.value = "Event"
            text_content.value = event_title.value
            event_title_summary.value = event_title.value
            event_location_summary.value = event_location.value
            event_start_summary.value = start_time_picker.value
            event_end_summary.value = end_time_picker.value
            extra_vis.visible=True
            event_summary_container.visible=True

        elif qr_type_dropdown.value == "Text":
            text_content.value=qr_url_input_field.value
            text_label.value = "Text"

        error_correction_content.value = error_correction_dropdown.value
        
        
    create_button = Button(
        icon=Icon(icon=Icons.ADD_ROUNDED, size=24), 
        content=Text(value="Generate a new QR code",size=24),
        on_click=lambda e: qr_creator_open(),
        align=Alignment.CENTER,
        height=70,
        style=ft.ButtonStyle(
            shape=RoundedRectangleBorder(radius=20)
        )
    )

    download_button = Button(
        icon=Icon(icon=Icons.DOWNLOAD_ROUNDED, size=20), 
        align=Alignment.CENTER,
        content=Text(value="Download",size=20),
        on_click=lambda e: show_download_confirm_dialog(),
        height=40,
        margin=Margin(right=5),
        style=ft.ButtonStyle(
            shape=RoundedRectangleBorder(radius=10),
            color=Colors.SURFACE_CONTAINER_LOW,
            bgcolor=Colors.PRIMARY,
            overlay_color=Colors.ON_PRIMARY_CONTAINER
        )
    )

    modify_text = Text(value="Modify settings",align=Alignment.CENTER,size=20,color=Colors.WHITE)
    clear_text = Text(value="Clear",size=20,color=Colors.RED_400)
    type_icon = Icon(icon=Icons.WIFI_ROUNDED,size=35)

    error_correction_content = Text(value="",size=20,color=Colors.PRIMARY)
    error_correction_container=Column(controls=[
        Text(value="Correction",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
        Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER , content=error_correction_content),
    ])

    text_content = Text(value="",size=20,color=Colors.PRIMARY)
    text_label = Text(value="",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE))

    wifi_protocol = Text(value="",size=20)
    wifi_pass = Text(value="",size=20)
    wifi_pass_display = Column(controls=[
        Text(value="Password",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
        Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER, content=wifi_pass),
    ])

    wifi_subcontainer = Row(visible=False,controls=[       
        Column(controls=[
            Text(value="Security",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
                Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER, content=Row(controls=[
                    Icon(icon=Icons.SHIELD_ROUNDED),
                    wifi_protocol      
                ])),
        ]),
        wifi_pass_display,
    ])      

    def get_content_container(label,content):
        content_container=Column(controls=[
            label,
            Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER, content=content),
        ])
        return content_container

    preview_qr_on_summary = Container()

    filename_textfield = TextField(
        expand=False,
        label="Enter filename",
        hint_text="QR name here",
        border_width=0,
    )

    email_subject_summary =Text(value="",align=Alignment.CENTER,size=20,color=Colors.WHITE)
    email_body_summary =Text(value="",align=Alignment.CENTER,size=20,color=Colors.WHITE)

    email_advanced_container = Column(tight=True,controls=[
        #get_content_container("subject",Text(value=email_subject.value,size=20,color=Colors.PRIMARY)),
        Column(controls=[
            Text(value="Subject",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
            Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER, content=email_subject_summary),
        ]),
        Column(controls=[
            Text(value="Body",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
            Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER, content=email_body_summary),
        ])
    ])

    longitude=Text(value="",size=20,color=Colors.PRIMARY)

    longitude_container = Column(controls=[
        Text(value="Longitude",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
        Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER, content=longitude),
    ])

    sms_msg = Text(value="",size=20,color=Colors.PRIMARY)

    sms_container = Column(visible=False,controls=[
        Text(value="Message",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
        Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER, content=sms_msg),
    ])

    event_title_summary = Text(value="",size=20,color=Colors.PRIMARY)
    event_location_summary = Text(value="",size=20,color=Colors.PRIMARY)
    event_start_summary = Text(value="",size=20,color=Colors.PRIMARY)
    event_end_summary = Text(value="",size=20,color=Colors.PRIMARY)
    
    event_summary_container = Column(visible=False, controls=[
        Column(controls=[
            Text(value="Location",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
            Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER, content=event_location_summary),
        ]),
        Column(controls=[
            Text(value="Start",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
            Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER, content=event_start_summary),
        ]),
        Column(controls=[
            Text(value="End",size=15,margin=Margin(bottom=-5),style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
            Container(border_radius=10,padding=10, bgcolor=Colors.SURFACE_CONTAINER, content=event_end_summary),
        ]),
    ])

    extra_vis= Container(
        bgcolor=Colors.SECONDARY_CONTAINER,
        border_radius=20,
        padding=10,
        visible=False,
        expand=False,
        align=Alignment.CENTER,
        content=Row(tight=True,controls=[
            email_advanced_container,
            sms_container,
            event_summary_container,
            #get_qr_content()
        ])
    )

    summary_visual = Column(tight=True,controls=[
        Container(padding=20,border_radius=30,align=Alignment.CENTER,bgcolor=Colors.INVERSE_PRIMARY,content=preview_qr_on_summary),
        Container(
            bgcolor=Colors.SURFACE_CONTAINER,
            border_radius=20,
            padding=5,
            expand=False,
            align=Alignment.CENTER,
            content=Row(tight=True,controls=[
                filename_textfield,
                Container(height=30,width=2,bgcolor="grey",margin=Margin(left=5,right=5),content=Text("")),     
                #error_correction_container,
                download_button,
            ])
        ),
        Row(alignment=ft.MainAxisAlignment.CENTER,margin=Margin(top=40),controls=[
            Container(on_hover=lambda e: handle_modify_hover(e, modify_text,Colors.WHITE,Colors.WHITE),on_click=lambda e:qr_creator_open(),content=modify_text),
            Container(height=20,width=2,bgcolor="grey",margin=Margin(left=5,right=5),content=Text("")),
            Container(on_hover=lambda e: handle_modify_hover(e, clear_text,Colors.RED_200,Colors.RED_400),on_click=lambda e:clear_summary(),content=clear_text),
        ]),
        Container(
            bgcolor=Colors.SECONDARY_CONTAINER,
            border_radius=30,
            padding=10,
            expand=False,
            align=Alignment.CENTER,
            content=Row(tight=True,controls=[
                Container(padding=15,border_radius=20,border=Border.all(width=4,color=Colors.PRIMARY),bgcolor=Colors.PRIMARY_CONTAINER,content=type_icon),
                get_content_container(text_label,text_content),
                wifi_subcontainer,
                longitude_container,
                error_correction_container,
            ])
        ),
        extra_vis,
    ])

    def handle_modify_hover(e,element,color=Colors.WHITE,default_color=Colors.PRIMARY):
        if e.data == True:
            element.color = color
            element.style = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE,decoration_color=color)
        else:
            element.color = default_color
            element.style = None


    bmac_button_top_bar = Button(
        icon=Icons.COFFEE_ROUNDED,
        content="Buy me a coffee",
        visible=True,
        color="yellow",
        #bgcolor=Colors.YELLOW_900,
        icon_color="yellow",
        #on_click=lambda e:asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR","BLANK"))
    )

    top_bar = Row(controls=[
        Row(controls=[
            Text(value="QuickeR",size=24,weight=ft.FontWeight.BOLD,margin=Margin(left=10)),
        ]),
        Container(
            border_radius=10,
            bgcolor=Colors.TERTIARY_CONTAINER,
            content=Text(
                value="Web",
                size=11,
                color=Colors.WHITE,
                style=ft.TextStyle(weight=ft.FontWeight.BOLD)
            ),
            border=Border.all(width=3,color=Colors.TERTIARY),
            padding=7
        ),
        Container(expand=True),
        Row(
            alignment=ft.MainAxisAlignment.END,
            controls=[
                #appearance_setting,
                bmac_button_top_bar,
                IconButton(
                    icon=get_github_icon_by_mode(),
                    on_click=lambda e:asyncio.ensure_future(open_url("https://github.com/ChoiceZero/QuickeR-Web","BLANK"))
                ),
                Button(
                    icon=Icons.INFO_OUTLINE_ROUNDED,
                    content="About",
                    on_click=lambda e: open_about_bs()
                ),
            ],
        )
    ])

    overview = Column(
        alignment=ft.MainAxisAlignment.CENTER,
        expand=True,
        controls=[create_button],
    )

    async def open_url(url_to_open,target: ft.UrlTarget):
        url = url_to_open
        await ft.UrlLauncher().launch_url(ft.Url(url=url, target=target))

    safearea = ft.SafeArea(
        content=Column(
            expand=True,
            controls=[top_bar,overview,Container(height=150)]
        ),
        expand=True
    )
    page.add(safearea)


    page.overlay.append(create_layout)

    #Updates the app on resize
    def resize_handler():
        if page.width < 600:
            bmac_button_top_bar.visible = False
        else:
            bmac_button_top_bar.visible = True
    resize_handler()

    #Initial exec functions
    page.on_resize = resize_handler
    display_preview_qr("","black","white",ERROR_CORRECTION_MAP["M (15%)"])

#Run the app
ft.run(main, assets_dir="program_variants/assets")