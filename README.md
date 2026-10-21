# Dead as Disco Sync

[English below](#english)

Ссылка на YouTube или аудиофайл → WAV и настройки для «Моя музыка» в Dead as Disco: **Темп**, **Смещение ритма (мс)**, **Время начала (с)**, **Время окончания (с)**. Проверено в игре.

## Запуск (Windows)

1. Скачать один файл: **[DeadAsDiscoSync.bat](https://github.com/flipasd-108/dead-as-disco-sync/releases/latest/download/DeadAsDiscoSync.bat)** и положить в отдельную папку.
2. Запустить его: откроется окно. Вставить ссылку или выбрать файл (аудио или видео) и нажать «Старт». Готовые песни копятся в списке, двойной щелчок по песне открывает её папку. Можно и просто перетащить файл на батник. Windows может спросить «Запустить?», ответить «да».
3. Песня **сама добавляется в «Мою музыку»**, если в игре уже есть хоть одна песня. Папку с песнями в сохранениях игры (`%LOCALAPPDATA%\Pagoda\Saved\ImportedSongs`) программа находит сама, её можно указать и вручную. Потом перезапустить игру: Reload Directory новые песни не видит. Если песня не появилась, добавить WAV из папки `songs\`.
4. В игре открыть песню и нажать **«Автоматическое определение»**. Трек уже начинается на доле, и игра сама ставит темп и смещение. Числа из программы нужны, только если автоопределение промахнулось.

Первый запуск сам ставит [uv](https://github.com/astral-sh/uv), Python, библиотеки и модели (~1 ГБ, несколько минут). Дальше на 3-минутную песню около 12 с, с плавающим темпом около 40 с.

Если есть видеокарта NVIDIA, окно при первом запуске предложит считать на ней: обычная песня ~5 с вместо ~12 с, но один раз докачается около 2,5 ГБ (на диске ещё ~4 ГБ). Потом это меняется переключателем под списком песен, выбор хранится в `songs\gpu.txt`. Видеокарты AMD и Intel не поддерживаются.

Фон окна — обои из игры, они скачиваются при первом запуске в `songs\background.png`. Свою картинку можно положить туда же под именем `background.png` или `background.jpg`.

**Грузить в игру именно этот WAV и не перемещать его**: смещение измерено на нём, MP3 того же трека может быть сдвинут на десятки мс.

## Как считает

- доли находят три независимо обученные модели [Beat This!](https://github.com/CPJKU/beat_this) (CPJKU, 2024), темп — медиана их голосов;
- через все доли методом наименьших квадратов проводится ровная сетка: темп до сотых (почти целый ставится целым);
- смещение: голоса трёх моделей плюс голос по атакам ударов (точность 1 мс); если атаки согласны с моделями в пределах 12 мс, берутся атаки, иначе медиана моделей; в конце печатается сверка;
- если темп плавает больше чем на 20 мс (живой барабанщик), выдаются два варианта: оригинал без изменений и выровненная копия `(sync)`, где звук между ударами чуть растянут/сжат (±1–2%) и все удары ложатся на ровную сетку; хватает обычного режима без расширенного редактора;
- за образец для выравнивания берётся модель с самой чистой сеткой: если одна модель в каком-то куске перешла на удвоенный счёт, она не портит результат.
- WAV подрезается так, чтобы начинаться ровно на доле (разработчики: игре нужен «BPM и трек, обрезанный так, что начинается на доле»): тишина до первой доли отрезается, а если там затакт — добавляется тишина до доли перед ним. Поэтому **смещение всегда 0, начало 0**, вбивать по сути нужно только темп;
- для треков медленнее 120 подсказывается удвоенный темп (игра советует 120–200).

Если YouTube просит подтвердить, что вы не бот, программа повторяет попытку и пробует вход из Firefox. Не помогло: войти в YouTube в Firefox, или в Chrome поставить расширение «Get cookies.txt LOCALLY», на youtube.com нажать Export и положить `cookies.txt` рядом с батником, или скачать песню и перетащить файл.

Подходят и ссылки с других сайтов, которые знает [yt-dlp](https://github.com/yt-dlp/yt-dlp) (SoundCloud, Bandcamp, VK...). Spotify и Яндекс Музыка — нет.

## English

YouTube link or audio file → WAV plus the **My Music** settings for Dead as Disco: **BPM**, **Beat Offset (ms)**, **Start Time (s)**, **End Time (s)**. Tested in game.

1. Download one file: **[DeadAsDiscoSync.bat](https://github.com/flipasd-108/dead-as-disco-sync/releases/latest/download/DeadAsDiscoSync.bat)** into its own folder.
2. Run it: a window opens. Paste a link or pick a file (audio or video) and press Start. Finished songs pile up in a list; double-click one to open its folder. Dropping a file onto the .bat works too.
3. The song is **added to My Music automatically** if the game already has at least one song. The songs folder in the game's saves (`%LOCALAPPDATA%\Pagoda\Saved\ImportedSongs`) is found automatically, or you can pick it. Restart the game: Reload Directory doesn't pick up new songs. If the song isn't there, add the WAV from `songs\`.
4. In the game open the song and press **Auto-detect**. The track already starts on a beat, so the game sets tempo and offset itself. The numbers the tool prints are only for when auto-detect misses.

The first run installs uv, Python, libraries and models (~1 GB). Output is in English unless Windows is set to Russian.

With an NVIDIA card the window offers to use it on the first start: a regular song takes ~5 s instead of ~12 s, after a one-time 2.5 GB download (~4 GB on disk). The switch under the song list changes it later; the choice is kept in `songs\gpu.txt`. AMD and Intel cards aren't supported.

The window's background is game art, fetched on the first start into `songs\background.png`; put your own `background.png` or `background.jpg` there to replace it.

How it works: the WAV is trimmed (or padded) to start exactly on a beat, so Beat Offset is always 0 and Start Time 0, as the developers ask; three independently trained Beat This! models vote on beats and BPM; a least-squares constant grid gives BPM to 0.01; the offset is the attacks vote (1 ms resolution) when it agrees with the models within 12 ms, otherwise the models' median. If the tempo drifts more than 20 ms (live drummer), you get two options: the untouched original and a `(sync)` copy time-warped by 1–2% between beats onto one constant tempo, so a single BPM fits the whole song.

If YouTube asks to confirm you're not a bot: sign in to YouTube in Firefox, or export `cookies.txt` with the "Get cookies.txt LOCALLY" extension and put it next to the .bat, or download the song yourself and drop the file.

---

Без батника / without the .bat: `uv run disco_sync.py "<url or file>" [out_dir]`. Licence: MIT.
Идея и формат полей / idea and field format: [Aoshi2020/DeadAsDisco-SyncTool](https://github.com/Aoshi2020/DeadAsDisco-SyncTool).
