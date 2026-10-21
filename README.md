# Dead as Disco Sync

[English below](#english)

Программа для «Моей музыки» в Dead as Disco. Берёт песню с YouTube или из файла, находит доли, подрезает трек так, чтобы он начинался ровно на доле, и сама добавляет его в игру. В игре остаётся нажать «Автоматическое определение». Проверено в игре на стриме.

## Требования

- Windows 10 или 11.
- Интернет при каждом запуске: батник берёт программу из последнего релиза на GitHub. Первый запуск ещё скачивает около 1 ГБ, с видеокартой ещё около 2,5 ГБ.
- Место на диске: около 1 ГБ, с видеокартой ещё около 4 ГБ.
- Dead as Disco на этом же компьютере, и в «Моей музыке» уже есть хотя бы одна песня, добавленная через игру. Иначе программа сделает WAV, но добавить его в игру придётся вручную.
- Видеокарта NVIDIA не обязательна.

Скачивать нужно только DeadAsDiscoSync.bat, остальное он поставит сам. Кто пользовался версией до 1.6, скачивает батник заново: старый открывает консоль вместо окна. Своего `disco_sync.py` рядом с батником быть не должно, иначе батник запустит его вместо свежей версии.

## Запуск (Windows)

1. Скачать **[DeadAsDiscoSync.bat](https://github.com/flipasd-108/dead-as-disco-sync/releases/latest/download/DeadAsDiscoSync.bat)** и положить в отдельную папку: рядом появится папка `songs` с готовыми песнями.
2. Запустить его. Если Windows предупредит о скачанном файле, разрешить запуск. Первый запуск ставит [uv](https://github.com/astral-sh/uv), Python, библиотеки и модели: около 1 ГБ, несколько минут. Чёрное окно консоли в это время не закрывать.
3. В окне программы проверить шаг 1, папку «Моей музыки» в сохранениях игры (`%LOCALAPPDATA%\Pagoda\Saved\ImportedSongs`). Обычно она находится сама, иначе указать её кнопкой «Указать». Программа добавляет песни, только если в игре уже есть хотя бы одна песня, добавленная через саму игру.
4. Вставить ссылку или выбрать файл и нажать «Старт». Следующие ссылки можно добавлять, пока идёт анализ: они встанут в очередь. Файл можно и перетащить на DeadAsDiscoSync.bat.
5. Перезапустить игру (Reload Directory новые песни не видит), открыть песню в «Моей музыке» и нажать **«Автоматическое определение»**. Трек уже начинается на доле, и игра сама ставит темп и смещение. Если она промахнулась, темп есть в списке песен программы.

Готовые песни собираются в списке. Кнопки над ним открывают папку песни, показывают WAV в Проводнике и удаляют песню: из списка, из игры и с диска, после подтверждения.

Если песня не появилась в игре, добавить в неё вручную WAV из папки `songs`: он подрезан по доле, а исходный MP3 нет. Потом этот WAV не перемещать.

Подходят файлы WAV, MP3, OGG, FLAC, AIFF, M4A, WMA, AAC (их принимает и сама игра), а ещё OPUS и видео MP4, MKV, WEBM, MOV. Ссылки подходят со всех сайтов, которые знает [yt-dlp]: YouTube, SoundCloud, Bandcamp, VK и другие. Spotify и Яндекс Музыка не подходят.

3-минутная песня обрабатывается около 12 с, с плавающим темпом около 40 с, плюс скачивание с YouTube.

### Видеокарта

Если есть видеокарта NVIDIA, при первом запуске программа предложит считать на ней. Обычная песня тогда обрабатывается около 5 с вместо 12, но один раз скачается ещё около 2,5 ГБ, а на диске займёт ещё около 4 ГБ. Включить или выключить можно переключателем под списком песен, это сработает после перезапуска программы. Видеокарты AMD и Intel не поддерживаются.

### Если YouTube не пускает

Если YouTube просит подтвердить, что вы не бот, программа повторяет попытку и пробует взять вход в YouTube из Firefox. Если не помогло:

- войти в YouTube в Firefox и запустить снова;
- или поставить в Chrome расширение «Get cookies.txt LOCALLY», на youtube.com нажать Export и положить `cookies.txt` рядом с DeadAsDiscoSync.bat;
- или скачать песню самому и выбрать файл.

### Фон окна

Обои из игры скачиваются при первом запуске в `songs\background.png`. Свою картинку можно положить туда же под именем `background.png` или `background.jpg`.

## Как это работает

Разработчики игры рассказали в [интервью 80.lv](https://80.lv/articles/interview-how-dead-as-disco-synchronizes-combat-to-player-uploaded-music), что игре нужен темп и трек, обрезанный так, чтобы он начинался на доле. Программа готовит именно такой трек.

- Доли ищут три независимо обученные модели [Beat This!](https://github.com/CPJKU/beat_this) (CPJKU, 2024). Через доли проводится ровная сетка методом наименьших квадратов, темп получается с точностью до сотых.
- Где стоит первая доля, решают голоса трёх моделей и голос по атакам ударов. Если атаки согласны с моделями в пределах 12 мс, берутся атаки, иначе медиана моделей.
- WAV подрезается до первой доли. Если перед ней затакт, в начало добавляется тишина до предыдущей доли. Поэтому смещение и время начала всегда 0.
- Если темп плавает больше чем на 20 мс (живой барабанщик), получается два варианта: оригинал и копия `(sync)`, где звук между ударами растянут или сжат на 1–2%, чтобы вся песня шла в одном темпе. В игру добавляются оба, лучше играть `(sync)`.

## English

A tool for Dead as Disco's **My Music**. It takes a song from YouTube or a file, finds the beats, trims the track to start exactly on a beat and adds it to the game. In the game you only press **Auto-detect**. Tested in game on stream.

Requirements:

- Windows 10 or 11.
- Internet on every start: the .bat fetches the tool from the latest GitHub release. The first start also downloads about 1 GB, about 2.5 GB more with the GPU option.
- Disk space: about 1 GB, about 4 GB more with the GPU option.
- Dead as Disco on the same PC, with at least one song already imported through the game. Otherwise the tool makes the WAV, but you add it to the game by hand.
- An NVIDIA card is optional.

DeadAsDiscoSync.bat is the only download; it installs the rest. If you used a version before 1.6, download the .bat again: the old one opens a console instead of the window. Don't keep a `disco_sync.py` of your own next to the .bat, or it runs that instead of the latest version.

Steps:

1. Download **[DeadAsDiscoSync.bat](https://github.com/flipasd-108/dead-as-disco-sync/releases/latest/download/DeadAsDiscoSync.bat)** into its own folder: a `songs` folder with the finished songs appears next to it.
2. Run it. If Windows warns about a downloaded file, allow it. The first run installs uv, Python, libraries and models: about 1 GB, a few minutes. Keep the black console window open meanwhile.
3. In the window check step 1, the My Music folder in the game's saves (`%LOCALAPPDATA%\Pagoda\Saved\ImportedSongs`). It's usually found automatically; otherwise press Pick. The tool adds songs only if the game already has at least one song imported through the game itself.
4. Paste a link or pick a file and press Start. You can add more links while one is analysed: they wait in a queue. Dropping a file onto DeadAsDiscoSync.bat works too.
5. Restart the game (Reload Directory doesn't pick up new songs), open the song in My Music and press **Auto-detect**. The track already starts on a beat, so the game sets tempo and offset itself. If it misses, the tempo is in the tool's song list.

Finished songs collect in a list. The buttons above it open the song's folder, show its WAV in Explorer and delete the song from the list, the game and the disk after a confirmation.

If a song doesn't show up in the game, add the WAV from the `songs` folder by hand: it's trimmed to the beat, the source MP3 isn't. Don't move that WAV afterwards.

Files: WAV, MP3, OGG, FLAC, AIFF, M4A, WMA, AAC (the game takes these too), plus OPUS and MP4, MKV, WEBM, MOV video. Links work from any site [yt-dlp] knows: YouTube, SoundCloud, Bandcamp, VK and more. Spotify and Yandex Music don't.

A 3-minute song takes about 12 s, about 40 s with a drifting tempo, plus the YouTube download. The window is in English unless Windows is set to Russian.

With an NVIDIA card the tool offers to use it on the first start: a regular song then takes about 5 s instead of 12, after a one-time download of about 2.5 GB and about 4 GB more on disk. The switch under the song list turns it on or off after a restart of the tool. AMD and Intel cards aren't supported.

If YouTube asks to confirm you're not a bot, the tool retries and tries your Firefox YouTube sign-in. If that fails, sign in to YouTube in Firefox and run again, or export `cookies.txt` with the "Get cookies.txt LOCALLY" Chrome extension and put it next to DeadAsDiscoSync.bat, or download the song yourself and pick the file.

The window's background is game art, fetched on the first start into `songs\background.png`. Put your own `background.png` or `background.jpg` there to replace it.

How it works. The developers said in an [80.lv interview](https://80.lv/articles/interview-how-dead-as-disco-synchronizes-combat-to-player-uploaded-music) that the game needs the tempo and a track cut to start on a beat, and that's what the tool prepares. Three independently trained [Beat This!](https://github.com/CPJKU/beat_this) models find the beats, and a least-squares grid through them gives the tempo to 0.01 BPM. The first beat is placed by the models' votes plus a vote from drum attacks: the attacks win when they agree with the models within 12 ms, otherwise the models' median does. The WAV is cut to that beat, or padded with silence back to the previous beat when there are pickup notes, so Beat Offset and Start Time are always 0.

If the tempo drifts more than 20 ms (a live drummer), you get two versions: the original and a `(sync)` copy stretched or squeezed by 1–2% between beats so the whole song runs at one tempo. Both go into the game; play the `(sync)` one.

---

Без окна / without the window: `uv run disco_sync.py "<url or file>" [out_dir]`. Licence: MIT.
Идея и формат полей / idea and field format: [Aoshi2020/DeadAsDisco-SyncTool](https://github.com/Aoshi2020/DeadAsDisco-SyncTool).

[yt-dlp]: https://github.com/yt-dlp/yt-dlp
