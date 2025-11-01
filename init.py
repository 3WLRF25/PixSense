def gtInit():
    import gettext, locale, sys, io, os
    if sys.stdout is not None:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    system_lang = locale.getlocale()[0]
    # system_lang = "en_US"
    locale_dir = os.path.join(os.path.dirname(__file__), 'locale')
    try:
        trans = gettext.translation(
            'messages', 
            locale_dir, 
            languages=[system_lang] if system_lang else None,
        )
        trans.install()
    except FileNotFoundError:
        gettext.install('messages', locale_dir)

def Init():
    gtInit()
