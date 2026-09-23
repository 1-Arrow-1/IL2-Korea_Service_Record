"""
Name and describe the second batch of USAF awards in six languages:

    601045-601046  Distinguished Unit Citation, 2nd and 3rd oak leaf cluster
    601047-601049  ROK Presidential Unit Citation, 2nd to 4th award (no devices)
    601050-601051  Silver Star, 3rd and 4th oak leaf cluster
    601052         Distinguished Service Medal
    601053         National Defense Service Medal
    601054-601057  Commendation Ribbon with Metal Pendant and three clusters
    601058-601062  Bronze Star Medal with "V" device and clusters (601059/601061
                   and 601060/601062 are twin ids for one rung, see awards.cfg)

    python tools/add_awards_batch2.py
    python tools/add_awards_batch2.py --dry-run

Names go into nsdata/assets/locale/awards.locale=<lang>.json after their
predecessor, following each file's own way of saying "oak leaf cluster"
(English "Bronze Oak Leaf Cluster in Lieu of 3rd ...", German "(drittes
Eichenlaub)", French "(3e agrafe feuille de chêne)", Spanish "(Tercer Racimo
de Hojas de Roble)", Russian "с тремя дубовыми листьями", Chinese
"（第三枚橡叶簇）"). The three new decorations get a full description; every
cluster rung gets the stock redirect line "#<base> // ..." that points the
game at its base award's text, written for all six languages. ROK citation
repeats instead use numbered award names and authorize no ribbon devices.
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from korea_service_record.assets import AssetResolver        # noqa: E402
from korea_service_record.locate import find_game_dir        # noqa: E402
from add_unit_citation import (LANGS, LOCALE, TEXTS, DUC_NAMES, ROK_NAMES,   # noqa: E402
                               set_or_insert_name)

REDIRECT = "#{base} // Использовать описание от другой награды"

# How each language writes "with the Nth cluster" onto a base name. The
# English key counts awards (3rd cluster = 4th award), the others clusters.
def cluster_name(lang: str, base: str, n: int, bronze: bool = False) -> str:
    if lang == "eng":
        nth = {2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}[n + 1]
        return f"Bronze Oak Leaf Cluster in Lieu of {nth} {base}"
    if lang == "ger":
        return f"{base} ({['erstes', 'zweites', 'drittes', 'viertes'][n - 1]} Eichenlaub)"
    if lang == "fra":
        ordinal = ["1re", "2e", "3e", "4e"][n - 1]
        return f"{base} ({ordinal} agrafe feuille de chêne{' bronze' if bronze else ''})"
    if lang == "spa":
        return f"{base} ({['Primer', 'Segundo', 'Tercer', 'Cuarto'][n - 1]} Racimo de Hojas de Roble)"
    if lang == "rus":
        count = ["с одним бронзовым дубовым листом" if bronze else "с одним дубовым листом",
                 "с двумя бронзовыми дубовыми листьями" if bronze else "с двумя дубовыми листьями",
                 "с тремя бронзовыми дубовыми листьями" if bronze else "с тремя дубовыми листьями",
                 "с четырьмя бронзовыми дубовыми листьями" if bronze else "с четырьмя дубовыми листьями"][n - 1]
        return f"{base} {count}"
    if lang == "chs":
        return f"{base}（第{'一二三四'[n - 1]}枚橡叶簇）"
    raise KeyError(lang)


SILVER_STAR = {"eng": "Silver Star", "ger": "Silver Star", "fra": "Silver Star",
               "spa": "Estrella de Plata", "rus": "Серебряная звезда", "chs": "银星勋章"}

DSM_NAMES = {"eng": "Distinguished Service Medal", "ger": "Distinguished Service Medal",
             "fra": "Distinguished Service Medal", "spa": "Medalla por Servicio Distinguido",
             "rus": "Медаль за выдающуюся службу", "chs": "杰出服役勋章"}

NDSM_NAMES = {"eng": "National Defense Service Medal", "ger": "National Defense Service Medal",
              "fra": "National Defense Service Medal", "spa": "Medalla de Servicio de Defensa Nacional",
              "rus": "Медаль за службу в национальной обороне", "chs": "国防服役奖章"}

# The base name each language builds the cluster names on; English uses the
# short form the stock file uses for its own "in Lieu of" names.
COMMENDATION_NAMES = {"eng": "Commendation Ribbon with Metal Pendant",
                      "ger": "Commendation Ribbon with Metal Pendant",
                      "fra": "Commendation Ribbon with Metal Pendant",
                      "spa": "Medalla de Encomio", "rus": "Медаль за похвальную службу",
                      "chs": "嘉奖奖章"}
COMMENDATION_SHORT = dict(COMMENDATION_NAMES, eng="Commendation Ribbon",
                          ger="Commendation Ribbon", fra="Commendation Ribbon")

DSM_DESCRIPTIONS = {
    "eng": """\
The Distinguished Service Medal is awarded to any person who, while serving in any capacity with the United States armed forces, has distinguished himself by exceptionally meritorious service to the Government in a duty of great responsibility. It is a decoration for the burden of command rather than for gallantry: the responsibility for a wing, a task force or a theatre, carried well over a long period.

The Army version was established by Act of Congress in July 1918 and is the one Air Force officers received throughout the Korean War, since the Air Force's own Distinguished Service Medal was not created until 1960. The medal is a gold-coloured eagle inside a dark blue enamel ring bearing the words FOR DISTINGUISHED SERVICE and the date MCMXVIII, suspended from a ribbon of scarlet with a white centre stripe edged in blue.

In Korea it went to the men who ran the air war: the commanders of Far East Air Forces and Fifth Air Force, of Bomber Command and the fighter wings, and a few group commanders whose units carried a campaign. For a squadron commander it marks the point at which he has grown beyond his own cockpit and become answerable for everyone else's.""",
    "ger": """\
Die Distinguished Service Medal wird an jeden verliehen, der sich im Dienst der Streitkräfte der Vereinigten Staaten durch außergewöhnlich verdienstvolle Leistungen für die Regierung in einer Stellung von großer Verantwortung ausgezeichnet hat. Sie ist eine Auszeichnung für die Last des Kommandos, nicht für Tapferkeit: die Verantwortung für ein Geschwader, einen Verband oder einen Kriegsschauplatz, über lange Zeit gut getragen.

Die Heeresversion wurde im Juli 1918 durch Beschluss des Kongresses gestiftet und ist diejenige, die Offiziere der Air Force während des gesamten Koreakrieges erhielten, da die eigene Distinguished Service Medal der Air Force erst 1960 geschaffen wurde. Die Medaille zeigt einen goldfarbenen Adler in einem dunkelblau emaillierten Ring mit der Inschrift FOR DISTINGUISHED SERVICE und der Jahreszahl MCMXVIII, getragen an einem scharlachroten Band mit weißem, blau eingefasstem Mittelstreifen.

In Korea ging sie an die Männer, die den Luftkrieg führten: die Kommandeure der Far East Air Forces und der Fifth Air Force, des Bomber Command und der Jagdgeschwader sowie an einige Gruppenkommandeure, deren Verbände eine Kampagne getragen hatten. Für einen Staffelkommandeur markiert sie den Punkt, an dem er über das eigene Cockpit hinausgewachsen ist und für alle anderen die Verantwortung trägt.""",
    "fra": """\
La Distinguished Service Medal est décernée à quiconque, servant à quelque titre que ce soit dans les forces armées des États-Unis, s'est distingué par des services exceptionnellement méritoires rendus au gouvernement dans une fonction de grande responsabilité. C'est une décoration pour le poids du commandement plutôt que pour la bravoure : la responsabilité d'une escadre, d'une force opérationnelle ou d'un théâtre, assumée avec succès sur une longue période.

La version de l'armée de terre fut créée par une loi du Congrès en juillet 1918 et c'est celle que les officiers de l'Air Force reçurent pendant toute la guerre de Corée, l'Air Force n'ayant sa propre Distinguished Service Medal qu'en 1960. La médaille représente un aigle doré dans un anneau d'émail bleu foncé portant les mots FOR DISTINGUISHED SERVICE et la date MCMXVIII, suspendu à un ruban écarlate à bande centrale blanche bordée de bleu.

En Corée, elle alla aux hommes qui dirigeaient la guerre aérienne : les commandants des Far East Air Forces et de la Fifth Air Force, du Bomber Command et des escadres de chasse, ainsi qu'à quelques commandants de groupe dont les unités avaient porté une campagne. Pour un commandant d'escadron, elle marque le moment où il a dépassé son propre cockpit pour répondre de tous les autres.""",
    "spa": """\
La Medalla por Servicio Distinguido se concede a cualquier persona que, sirviendo en cualquier calidad en las fuerzas armadas de los Estados Unidos, se haya distinguido por servicios excepcionalmente meritorios al Gobierno en un puesto de gran responsabilidad. Es una condecoración por la carga del mando más que por el valor: la responsabilidad de un ala, una fuerza operativa o un teatro de operaciones, llevada con acierto durante un largo periodo.

La versión del Ejército fue creada por ley del Congreso en julio de 1918 y es la que recibieron los oficiales de la Fuerza Aérea durante toda la guerra de Corea, ya que la Fuerza Aérea no tuvo su propia Medalla por Servicio Distinguido hasta 1960. La medalla es un águila dorada dentro de un anillo de esmalte azul oscuro con las palabras FOR DISTINGUISHED SERVICE y la fecha MCMXVIII, suspendida de una cinta escarlata con una franja central blanca ribeteada de azul.

En Corea la recibieron los hombres que dirigieron la guerra aérea: los comandantes de las Fuerzas Aéreas del Lejano Oriente y de la Quinta Fuerza Aérea, del Mando de Bombardeo y de las alas de caza, y unos pocos comandantes de grupo cuyas unidades sostuvieron una campaña. Para un comandante de escuadrón marca el momento en que ha crecido más allá de su propia cabina y responde por todos los demás.""",
    "rus": """\
Медаль за выдающуюся службу вручается любому, кто, служа в любом качестве в вооружённых силах Соединённых Штатов, отличился исключительно заслуженной службой правительству на посту большой ответственности. Это награда за бремя командования, а не за храбрость: ответственность за авиакрыло, оперативное соединение или театр военных действий, достойно нёсшаяся долгое время.

Армейский вариант был учреждён актом Конгресса в июле 1918 года, и именно его получали офицеры ВВС на протяжении всей Корейской войны, поскольку собственная медаль ВВС за выдающуюся службу была учреждена лишь в 1960 году. Медаль представляет собой золотистого орла в кольце тёмно-синей эмали с надписью FOR DISTINGUISHED SERVICE и датой MCMXVIII, подвешенного на алой ленте с белой центральной полосой, окаймлённой синим.

В Корее её получали те, кто руководил воздушной войной: командующие ВВС Дальнего Востока и Пятой воздушной армией, бомбардировочным командованием и истребительными крыльями, а также несколько командиров групп, чьи части вынесли на себе целую кампанию. Для командира эскадрильи она отмечает момент, когда он перерос собственную кабину и стал отвечать за всех остальных.""",
    "chs": """\
杰出服役勋章授予在美国武装部队中以任何身份服役、在重大责任岗位上为政府作出特别卓越贡献的人员。它是一枚表彰指挥重任而非英勇行为的勋章：长期出色地担负起一个联队、一支特遣部队或一个战区的责任。

陆军版本于1918年7月经国会法案设立，朝鲜战争期间空军军官获授的正是这一版本，因为空军自己的杰出服役勋章直到1960年才设立。勋章为一只金色的鹰，置于深蓝色珐琅圆环之内，环上铸有FOR DISTINGUISHED SERVICE字样和MCMXVIII年份，悬挂于一条中央为白色、两侧镶蓝边的猩红色绶带上。

在朝鲜，它授予了指挥空战的人：远东空军和第五航空队、轰炸机司令部及各战斗机联队的指挥官，以及少数几位所部撑起整个战役的大队长。对一位中队长而言，它标志着他已超越自己的座舱，开始为所有人负责。""",
}

NDSM_DESCRIPTIONS = {
    "eng": """\
The National Defense Service Medal recognises honourable active service in the armed forces of the United States during a period of national emergency. It asks nothing of the recipient but that he was in uniform when the country was at war: no action, no length of service, no rank.

It was established by Executive Order on 22 April 1953, in the last months of the fighting, and made retroactive to 27 June 1950, the day President Truman ordered American forces into Korea. The medal is bronze, an eagle with wings inverted standing on a sword and palm below the words NATIONAL DEFENSE; the ribbon is scarlet with a broad golden-yellow centre stripe edged in thin lines of white, blue, white and red. It was later awarded again for Vietnam, the Gulf War and the years after 2001, and became the one medal almost every American serviceman of the second half of the century wore.

Because it did not exist until the spring of 1953, no one in Korea wore it for the first three years of the war. It appears in a career only if the war lasts long enough, and then it arrives for everyone at once.""",
    "ger": """\
Die National Defense Service Medal würdigt ehrenhaften aktiven Dienst in den Streitkräften der Vereinigten Staaten während einer Zeit des nationalen Notstands. Sie verlangt vom Empfänger nichts weiter, als dass er Uniform trug, während das Land im Krieg war: keine Gefechtshandlung, keine Dienstzeit, keinen Rang.

Sie wurde am 22. April 1953, in den letzten Monaten der Kämpfe, durch Präsidentenerlass gestiftet und rückwirkend ab dem 27. Juni 1950 verliehen, dem Tag, an dem Präsident Truman amerikanische Truppen nach Korea befahl. Die Medaille ist aus Bronze und zeigt einen Adler mit gesenkten Schwingen auf Schwert und Palmzweig unter den Worten NATIONAL DEFENSE; das Band ist scharlachrot mit einem breiten goldgelben Mittelstreifen, eingefasst von schmalen Linien in Weiß, Blau, Weiß und Rot. Später wurde sie erneut für Vietnam, den Golfkrieg und die Jahre nach 2001 verliehen und wurde zur einen Medaille, die fast jeder amerikanische Soldat der zweiten Jahrhunderthälfte trug.

Da sie bis zum Frühjahr 1953 nicht existierte, trug sie in Korea in den ersten drei Kriegsjahren niemand. In einer Laufbahn erscheint sie nur, wenn der Krieg lange genug dauert, und dann kommt sie für alle auf einmal.""",
    "fra": """\
La National Defense Service Medal récompense un service actif honorable dans les forces armées des États-Unis pendant une période d'urgence nationale. Elle n'exige rien de son titulaire sinon d'avoir porté l'uniforme pendant que le pays était en guerre : ni action d'éclat, ni durée de service, ni grade.

Elle fut créée par décret présidentiel le 22 avril 1953, dans les derniers mois des combats, avec effet rétroactif au 27 juin 1950, jour où le président Truman engagea les forces américaines en Corée. La médaille est en bronze : un aigle aux ailes abaissées posé sur une épée et une palme, sous les mots NATIONAL DEFENSE ; le ruban est écarlate, avec une large bande centrale jaune d'or bordée de fins liserés blanc, bleu, blanc et rouge. Elle fut de nouveau attribuée pour le Vietnam, la guerre du Golfe et les années après 2001, devenant la médaille que portèrent presque tous les militaires américains de la seconde moitié du siècle.

N'existant pas avant le printemps 1953, personne en Corée ne la porta pendant les trois premières années de la guerre. Elle n'apparaît dans une carrière que si la guerre dure assez longtemps, et alors elle arrive pour tout le monde à la fois.""",
    "spa": """\
La Medalla de Servicio de Defensa Nacional reconoce el servicio activo honorable en las fuerzas armadas de los Estados Unidos durante un periodo de emergencia nacional. No exige al condecorado más que haber vestido el uniforme mientras el país estaba en guerra: ni acción de combate, ni tiempo de servicio, ni graduación.

Fue creada por orden ejecutiva el 22 de abril de 1953, en los últimos meses de los combates, con efecto retroactivo al 27 de junio de 1950, el día en que el presidente Truman ordenó la entrada de las fuerzas estadounidenses en Corea. La medalla es de bronce: un águila con las alas hacia abajo posada sobre una espada y una palma, bajo las palabras NATIONAL DEFENSE; la cinta es escarlata con una ancha franja central amarillo dorado ribeteada por finas líneas blanca, azul, blanca y roja. Volvió a concederse por Vietnam, la guerra del Golfo y los años posteriores a 2001, y se convirtió en la medalla que lució casi todo militar estadounidense de la segunda mitad del siglo.

Como no existió hasta la primavera de 1953, nadie la llevó en Corea durante los tres primeros años de la guerra. Aparece en una carrera solo si la guerra dura lo suficiente, y entonces llega para todos a la vez.""",
    "rus": """\
Медаль за службу в национальной обороне отмечает достойную действительную службу в вооружённых силах Соединённых Штатов в период чрезвычайного положения в стране. От награждённого не требуется ничего, кроме того, что он носил форму, пока страна воевала: ни боевых действий, ни выслуги, ни звания.

Она была учреждена указом президента 22 апреля 1953 года, в последние месяцы боёв, с обратной силой с 27 июня 1950 года — дня, когда президент Трумэн направил американские войска в Корею. Медаль бронзовая: орёл с опущенными крыльями, стоящий на мече и пальмовой ветви, под словами NATIONAL DEFENSE; лента алая с широкой золотисто-жёлтой центральной полосой, окаймлённой тонкими линиями белого, синего, белого и красного цветов. Позже её вновь вручали за Вьетнам, войну в Заливе и годы после 2001-го, и она стала той медалью, которую носил почти каждый американский военнослужащий второй половины века.

Поскольку до весны 1953 года её не существовало, первые три года войны в Корее её никто не носил. В карьере она появляется лишь тогда, когда война длится достаточно долго, — и тогда приходит ко всем сразу.""",
    "chs": """\
国防服役奖章表彰在国家紧急状态期间于美国武装部队中光荣服现役的人员。它对获授者别无要求，只需在国家处于战争时身着军装：无需战功，无需服役年限，无需军衔。

它于1953年4月22日、战事的最后几个月里经总统行政命令设立，并追溯至1950年6月27日——杜鲁门总统下令美军进入朝鲜的那一天。奖章为青铜质，一只垂翼的鹰立于剑与棕榈枝之上，其上铸有NATIONAL DEFENSE字样；绶带为猩红色，中央一道宽阔的金黄色条纹，两侧依次镶以白、蓝、白、红细线。此后它又为越南战争、海湾战争及2001年后的岁月再次颁发，成为二十世纪后半叶几乎每一名美国军人都佩戴的一枚奖章。

由于它直到1953年春才设立，战争的头三年里，朝鲜战场上无人佩戴它。它只在战争持续得足够久时才会出现在一段军旅生涯中——届时所有人会同时获得。""",
}

COMMENDATION_DESCRIPTIONS = {
    "eng": """\
The Commendation Ribbon with Metal Pendant is awarded for meritorious service or achievement of a lesser degree than that required for the Bronze Star. It is the decoration for the man who does the unglamorous work well: the wingman who has flown his missions, held his position and brought his aircraft home, and has no headline to show for it.

The Army created the Commendation Ribbon in December 1945 and added the bronze pendant in 1949, a hexagon bearing an eagle with a shield on its breast, hung from a myrtle-green ribbon with five narrow white stripes. Through the Korean War Air Force personnel received this Army pattern, since the Air Force did not have a Commendation Medal of its own until 1958; the Army renamed its version the Army Commendation Medal in 1960. Further awards are shown by bronze oak leaf clusters.

In a fighter-bomber squadron it was by far the most common decoration after the Air Medal, and the first many pilots received for anything other than the number of missions flown.""",
    "ger": """\
Das Commendation Ribbon with Metal Pendant wird für verdienstvolle Dienste oder Leistungen geringeren Grades verliehen, als sie für den Bronze Star gefordert werden. Es ist die Auszeichnung für den Mann, der die unspektakuläre Arbeit gut erledigt: den Rottenflieger, der seine Einsätze geflogen, seine Position gehalten und sein Flugzeug nach Hause gebracht hat, ohne dass eine Schlagzeile davon zeugt.

Das Heer schuf das Commendation Ribbon im Dezember 1945 und fügte 1949 den bronzenen Anhänger hinzu, ein Sechseck mit einem Adler, der einen Schild auf der Brust trägt, an einem myrtengrünen Band mit fünf schmalen weißen Streifen. Während des gesamten Koreakrieges erhielten Angehörige der Air Force dieses Heeresmuster, da die Air Force bis 1958 keine eigene Commendation Medal besaß; das Heer benannte seine Version 1960 in Army Commendation Medal um. Weitere Verleihungen werden durch bronzenes Eichenlaub angezeigt.

In einer Jagdbomberstaffel war es nach der Air Medal die bei weitem häufigste Auszeichnung und für viele Piloten die erste, die sie für etwas anderes als die Zahl ihrer Einsätze erhielten.""",
    "fra": """\
Le Commendation Ribbon with Metal Pendant récompense des services ou des réalisations méritoires d'un degré moindre que celui exigé pour la Bronze Star. C'est la décoration de celui qui fait bien le travail sans éclat : l'ailier qui a accompli ses missions, tenu sa place et ramené son avion, sans qu'aucune manchette n'en témoigne.

L'armée de terre créa le Commendation Ribbon en décembre 1945 et lui ajouta en 1949 le pendentif de bronze, un hexagone portant un aigle à l'écu sur la poitrine, suspendu à un ruban vert myrte à cinq fines rayures blanches. Pendant toute la guerre de Corée, le personnel de l'Air Force reçut ce modèle de l'armée de terre, l'Air Force n'ayant pas de Commendation Medal propre avant 1958 ; l'armée de terre rebaptisa la sienne Army Commendation Medal en 1960. Les attributions suivantes sont marquées par des agrafes feuille de chêne en bronze.

Dans un escadron de chasseurs-bombardiers, c'était de loin la décoration la plus courante après l'Air Medal, et la première que beaucoup de pilotes recevaient pour autre chose que le nombre de missions accomplies.""",
    "spa": """\
La Medalla de Encomio se concede por servicios o logros meritorios de grado inferior al exigido para la Estrella de Bronce. Es la condecoración de quien hace bien el trabajo sin brillo: el punto que ha volado sus misiones, mantenido su posición y traído su avión de vuelta, sin ningún titular que lo cuente.

El Ejército creó la Cinta de Encomio en diciembre de 1945 y le añadió en 1949 el colgante de bronce, un hexágono con un águila que lleva un escudo en el pecho, suspendido de una cinta verde mirto con cinco estrechas franjas blancas. Durante toda la guerra de Corea el personal de la Fuerza Aérea recibió este modelo del Ejército, pues la Fuerza Aérea no tuvo Medalla de Encomio propia hasta 1958; el Ejército rebautizó la suya como Army Commendation Medal en 1960. Las concesiones posteriores se indican con racimos de hojas de roble de bronce.

En un escuadrón de cazabombarderos fue con diferencia la condecoración más común después de la Medalla Aérea, y la primera que muchos pilotos recibieron por algo distinto del número de misiones voladas.""",
    "rus": """\
Медаль за похвальную службу вручается за заслуги или достижения меньшей степени, чем требуется для Бронзовой звезды. Это награда для того, кто хорошо делает неброскую работу: ведомого, который отлетал свои вылеты, держал строй и привёл самолёт домой, не попав ни в одну сводку.

Армия учредила Похвальную ленту в декабре 1945 года, а в 1949-м добавила к ней бронзовую подвеску — шестиугольник с орлом, несущим на груди щит, на миртово-зелёной ленте с пятью узкими белыми полосами. На протяжении всей Корейской войны личный состав ВВС получал именно этот армейский образец, так как собственной медали за похвальную службу у ВВС не было до 1958 года; в 1960 году армия переименовала свою в Army Commendation Medal. Повторные награждения обозначаются бронзовыми дубовыми листьями.

В эскадрилье истребителей-бомбардировщиков это была, безусловно, самая частая награда после Медали ВВС и для многих лётчиков — первая, полученная не за число вылетов.""",
    "chs": """\
嘉奖奖章授予功绩或成就程度低于铜星勋章标准的有功人员。它是一枚表彰默默把工作做好的人的奖章：那位飞完了自己的任务、守住了位置、把飞机带回家，却没有任何头条新闻可言的僚机飞行员。

陆军于1945年12月设立嘉奖绶带，并于1949年增加青铜挂饰——一枚六边形，上有一只胸前佩盾的鹰，悬挂于一条带五道细白条纹的桃金娘绿色绶带上。整个朝鲜战争期间，空军人员获授的都是这一陆军式样，因为空军直到1958年才有自己的嘉奖奖章；陆军则于1960年将其版本更名为陆军嘉奖奖章。再次获授以青铜橡叶簇表示。

在一个战斗轰炸机中队里，它是仅次于空军奖章的最常见的奖励，也是许多飞行员因出击次数以外的事由获得的第一枚奖章。""",
}


BSV_NAMES = {"eng": "Bronze Star Medal with V Device", "ger": "Bronze Star Medal (V-Spange)",
             "fra": "Bronze Star Medal (agrafe V)", "spa": "Medalla Estrella de Bronce con Distintivo V",
             "rus": "Бронзовая звезда со знаком V", "chs": "铜星勋章（V字饰）"}


def bsv_cluster_name(lang: str, n: int) -> str:
    """The V ladder's cluster names, on each language's own stem."""
    if lang == "eng":
        nth = {2: "2nd", 3: "3rd"}[n + 1]
        return f"Bronze Oak Leaf Cluster in Lieu of {nth} Bronze Star Medal with V Device"
    if lang == "ger":
        return f"Bronze Star Medal (V-Spange, {['erstes', 'zweites'][n - 1]} Eichenlaub)"
    if lang == "fra":
        return f"Bronze Star Medal (agrafe V, {['1re', '2e'][n - 1]} agrafe feuille de chêne)"
    if lang == "spa":
        return f"Medalla Estrella de Bronce con Distintivo V ({['Primer', 'Segundo'][n - 1]} Racimo de Hojas de Roble)"
    if lang == "rus":
        return "Бронзовая звезда со знаком V " + ["с одним дубовым листом", "с двумя дубовыми листьями"][n - 1]
    if lang == "chs":
        return f"铜星勋章（V字饰，第{'一二'[n - 1]}枚橡叶簇）"
    raise KeyError(lang)


BSV_DESCRIPTIONS = {
    "eng": """\
The Bronze Star Medal is awarded for heroic or meritorious achievement or service in connection with military operations against an armed enemy. The two are the same medal, but Army regulations in force in 1950 told them apart: when the award was made for heroism, a bronze letter V - for valour - was worn on the suspension ribbon and on the service ribbon. Only one V was worn, however many of a man's Bronze Stars had been for heroism; every further award, for valour or for merit, added a bronze oak leaf cluster beside it.

For a pilot the V marked the sortie that was hard rather than the one with the biggest score: a single enemy aircraft shot down in a fight that did not go his way, a strike pressed home through the flak until the target was wrecked, or a mission finished with a wound. The degree of heroism was less than that required for the Silver Star, and in Korea the V-device Bronze Star was the decoration that most often separated the man who had been in a fight from the man who had flown his missions.

The Air Force used the Army's medal and the Army's rules throughout the war. Established by Executive Order in February 1944, the medal is a bronze star with a smaller star at its centre, on a ribbon of scarlet with a narrow blue centre stripe edged in white.""",
    "ger": """\
Die Bronze Star Medal wird für heldenhafte oder verdienstvolle Leistungen im Zusammenhang mit militärischen Operationen gegen einen bewaffneten Feind verliehen. Beides ist dieselbe Medaille, doch die 1950 geltenden Heeresvorschriften unterschieden sie: Wurde die Auszeichnung für Heldenmut verliehen, trug man am Ordensband und am Bandsteg ein bronzenes V - für valor, Tapferkeit. Nur ein V wurde getragen, gleichgültig wie viele Bronze Stars eines Mannes für Heldenmut verliehen worden waren; jede weitere Verleihung, ob für Tapferkeit oder für Verdienst, fügte daneben ein bronzenes Eichenlaub hinzu.

Für einen Piloten kennzeichnete das V den harten Einsatz, nicht den mit dem größten Ergebnis: ein einzelnes abgeschossenes Feindflugzeug in einem Gefecht, das nicht nach seinem Willen lief, ein durch die Flak bis zur Zerstörung des Ziels durchgeführter Angriff oder ein trotz Verwundung zu Ende geflogener Auftrag. Der Grad des Heldenmuts lag unter dem für den Silver Star geforderten, und in Korea war der Bronze Star mit V die Auszeichnung, die am häufigsten den Mann, der gekämpft hatte, von dem unterschied, der seine Einsätze geflogen war.

Die Air Force verwendete während des ganzen Krieges die Medaille und die Regeln des Heeres. Die im Februar 1944 durch Präsidentenerlass gestiftete Medaille ist ein bronzener Stern mit einem kleineren Stern in der Mitte an einem scharlachroten Band mit schmalem, weiß eingefasstem blauem Mittelstreifen.""",
    "fra": """\
La Bronze Star Medal récompense un acte ou des services héroïques ou méritoires accomplis dans le cadre d'opérations militaires contre un ennemi armé. C'est la même médaille dans les deux cas, mais les règlements de l'armée de terre en vigueur en 1950 les distinguaient : lorsque l'attribution récompensait l'héroïsme, une lettre V de bronze - pour valor, la bravoure - était portée sur le ruban de suspension et sur le ruban de rappel. On ne portait qu'un seul V, quel que soit le nombre de Bronze Stars reçues pour héroïsme ; chaque attribution supplémentaire, pour bravoure ou pour mérite, ajoutait à côté une agrafe feuille de chêne en bronze.

Pour un pilote, le V marquait la sortie difficile plutôt que celle au plus beau tableau : un seul avion ennemi abattu dans un combat mal engagé, une attaque poussée à travers la flak jusqu'à la destruction de l'objectif, ou une mission achevée malgré une blessure. Le degré d'héroïsme requis était inférieur à celui de la Silver Star, et en Corée la Bronze Star avec V fut la décoration qui, le plus souvent, distinguait l'homme qui s'était battu de celui qui avait accompli ses missions.

L'Air Force utilisa pendant toute la guerre la médaille et les règles de l'armée de terre. Créée par décret présidentiel en février 1944, la médaille est une étoile de bronze portant une étoile plus petite en son centre, sur un ruban écarlate à étroite bande centrale bleue bordée de blanc.""",
    "spa": """\
La Medalla Estrella de Bronce se concede por actos o servicios heroicos o meritorios en relación con operaciones militares contra un enemigo armado. Ambos casos son la misma medalla, pero los reglamentos del Ejército vigentes en 1950 los distinguían: cuando la concesión era por heroísmo, se llevaba una letra V de bronce -por valor- en la cinta de suspensión y en el pasador. Solo se llevaba una V, por muchas Estrellas de Bronce por heroísmo que hubiera recibido un hombre; cada concesión posterior, por valor o por mérito, añadía a su lado un racimo de hojas de roble de bronce.

Para un piloto, la V señalaba la salida difícil y no la de mayor tanteo: un solo avión enemigo derribado en un combate que no iba a su favor, un ataque llevado a través del fuego antiaéreo hasta destruir el objetivo, o una misión terminada con una herida. El grado de heroísmo exigido era menor que el de la Estrella de Plata, y en Corea la Estrella de Bronce con V fue la condecoración que con más frecuencia distinguía al hombre que había combatido del que había volado sus misiones.

La Fuerza Aérea usó la medalla y las normas del Ejército durante toda la guerra. Creada por orden ejecutiva en febrero de 1944, la medalla es una estrella de bronce con otra menor en el centro, sobre una cinta escarlata con una estrecha franja central azul ribeteada de blanco.""",
    "rus": """\
Бронзовая звезда вручается за героические или заслуженные действия либо службу в связи с военными операциями против вооружённого противника. В обоих случаях это одна и та же медаль, но армейские правила, действовавшие в 1950 году, различали их: если награда вручалась за героизм, на ленте медали и на планке носилась бронзовая литера V - valor, доблесть. Носили лишь одну литеру V, сколько бы Бронзовых звёзд за героизм ни было у человека; каждое последующее награждение, за доблесть или за заслуги, добавляло рядом бронзовый дубовый лист.

Для лётчика V отмечала трудный вылет, а не самый результативный: один сбитый самолёт противника в бою, который складывался не в его пользу, удар, доведённый сквозь зенитный огонь до уничтожения цели, или задание, завершённое несмотря на ранение. Требуемая степень героизма была ниже, чем для Серебряной звезды, и в Корее Бронзовая звезда со знаком V была той наградой, которая чаще всего отличала человека, побывавшего в бою, от того, кто просто отлетал свои вылеты.

ВВС на протяжении всей войны пользовались армейской медалью и армейскими правилами. Учреждённая указом президента в феврале 1944 года, медаль представляет собой бронзовую звезду с меньшей звездой в центре на алой ленте с узкой синей центральной полосой, окаймлённой белым.""",
    "chs": """\
铜星勋章授予在针对武装敌人的军事行动中作出英勇或卓越功绩、或提供相应服务的人员。两者是同一枚勋章，但1950年施行的陆军条例对其加以区分：凡因英勇行为授勋者，在勋章绶带及略章上佩戴一枚青铜字母V——代表valor，即英勇。无论一个人因英勇获授过多少枚铜星勋章，只佩戴一枚V；此后每一次授勋，无论因英勇还是因功绩，都在其旁增加一枚青铜橡叶簇。

对飞行员而言，V标志的是艰难的一次出击，而非战果最大的一次：在一场形势不利的空战中击落一架敌机、顶着高射炮火将攻击贯彻到目标被摧毁，或者带伤完成任务。所要求的英勇程度低于银星勋章，而在朝鲜，带V字饰的铜星勋章是最常把打过仗的人与飞完了任务的人区分开来的那枚勋章。

整个战争期间，空军沿用陆军的勋章和陆军的规则。该勋章于1944年2月经总统行政命令设立，为一枚中心带有较小五角星的青铜五角星，悬挂于一条中央有细蓝条纹、两侧镶白边的猩红色绶带上。""",
}


def redirect(base: str) -> dict:
    return {lang: REDIRECT.format(base=base) for lang in LANGS}


def names_for(base: dict, n: int, bronze: bool = False) -> dict:
    return {lang: cluster_name(lang, base[lang], n, bronze) for lang in LANGS}


def rok_names(number: int) -> dict:
    """Repeat citations are recorded by number, never as ribbon devices."""
    ordinal = {2: "2nd", 3: "3rd", 4: "4th"}[number]
    suffixes = {
        "eng": f" ({ordinal} award)",
        "ger": f" ({number}. Verleihung)",
        "fra": f" ({number}e attribution)",
        "spa": f" ({number}.ª concesión)",
        "rus": f" ({number}-е награждение)",
        "chs": f"（第{number}次授予）",
    }
    return {lang: ROK_NAMES[lang] + suffixes[lang] for lang in LANGS}


# (award id, inserted after, names, descriptions); insertion order matters.
AWARDS = (
    ("601045", "601044", names_for(DUC_NAMES, 2, True), redirect("601044")),
    ("601046", "601045", names_for(DUC_NAMES, 3, True), redirect("601044")),
    ("601047", "601046", rok_names(2), redirect("601043")),
    ("601048", "601047", rok_names(3), redirect("601043")),
    ("601049", "601048", rok_names(4), redirect("601043")),
    ("601050", "601049", names_for(SILVER_STAR, 3), redirect("601018")),
    ("601051", "601050", names_for(SILVER_STAR, 4), redirect("601018")),
    ("601052", "601051", DSM_NAMES, DSM_DESCRIPTIONS),
    ("601053", "601052", NDSM_NAMES, NDSM_DESCRIPTIONS),
    ("601054", "601053", COMMENDATION_NAMES, COMMENDATION_DESCRIPTIONS),
    ("601055", "601054", names_for(COMMENDATION_SHORT, 1), redirect("601054")),
    ("601056", "601055", names_for(COMMENDATION_SHORT, 2), redirect("601054")),
    ("601057", "601056", names_for(COMMENDATION_SHORT, 3), redirect("601054")),
    ("601058", "601057", BSV_NAMES, BSV_DESCRIPTIONS),
    ("601059", "601058", {l: bsv_cluster_name(l, 1) for l in LANGS}, redirect("601058")),
    ("601060", "601059", {l: bsv_cluster_name(l, 2) for l in LANGS}, redirect("601058")),
    ("601061", "601060", {l: bsv_cluster_name(l, 1) for l in LANGS}, redirect("601058")),
    ("601062", "601061", {l: bsv_cluster_name(l, 2) for l in LANGS}, redirect("601058")),
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    game = find_game_dir()
    if game is None:
        raise SystemExit("No IL-2 Korea installation found")
    res = AssetResolver(game)
    data = game / "data"
    import json

    for lang in LANGS:
        vpath = f"{LOCALE}/awards.locale={lang}.json"
        original = res.read(vpath)
        if original is None:
            print(f"  {lang}: {vpath} not found, skipped")
            continue
        text = original.decode("utf-8")
        patched = text
        for award, after, names, _ in AWARDS:
            patched = set_or_insert_name(patched, lang, award, after, names)
        json.loads(patched)
        name_changed = patched != text

        pending = []
        for award, _, _, descriptions in AWARDS:
            body = descriptions[lang].replace("\n", "\r\n").encode("utf-8")
            tpath = data / Path(TEXTS) / f"{award}.locale={lang}.txt"
            if not tpath.is_file() or tpath.read_bytes() != body:
                pending.append((award, tpath, body))

        state = []
        if name_changed:
            state.append(f"{len(AWARDS)} names")
        if pending:
            state.append(f"{len(pending)} descriptions")
        print(f"  {lang}: {'; '.join(state) or 'complete already'}")
        if args.dry_run:
            for award, _, names, _ in AWARDS:
                print(f"      {award}  {names[lang]}")
            continue
        if name_changed:
            out = data / Path(LOCALE) / f"awards.locale={lang}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(patched.encode("utf-8"))
        for _, tpath, body in pending:
            tpath.parent.mkdir(parents=True, exist_ok=True)
            tpath.write_bytes(body)
            b = tpath.read_bytes()
            assert not b.startswith(b"\xef\xbb\xbf") and b.count(b"\n") == b.count(b"\r\n")

    print("\n  --dry-run: nothing written" if args.dry_run else "\n  written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
