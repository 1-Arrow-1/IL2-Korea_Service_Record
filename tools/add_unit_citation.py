"""
Name and describe the unit citations in six languages: the Distinguished
Unit Citation (601042) and the Republic of Korea Presidential Unit Citation
(601043).

    python tools/add_unit_citation.py
    python tools/add_unit_citation.py --dry-run

Two things per language and award, matching what the game expects:

  * a name in  nsdata/assets/locale/awards.locale=<lang>.json   (key award<id>)
  * a description in  nsdata/assets/awards/6xx/<id>.locale=<lang>.txt

The two are the two kinds of unit award a Korean War wing could hold: the
DUC for one extraordinary action (the unit equivalent of the Distinguished
Service Cross), the ROK PUC for sustained service — Syngman Rhee's government
gave it to nearly every UN air unit that fought there.

Names follow each file's own convention for American decorations: English,
German and French keep the proper name (they keep "Silver Star" too), while
Spanish, Russian and Chinese translate it, as they do "Estrella de Plata",
"Серебряная звезда" and "银星勋章".

Descriptions are three paragraphs of history in the register of the ones the
mod already ships. Written UTF-8 without BOM, CRLF, blank line between
paragraphs — the shipped convention, checked byte-wise after writing.

The JSON edit is textual, inserted after award601041, so the other keys keep
their exact bytes. Idempotent: an existing key is updated to the table, and
an unchanged file is left alone.
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from korea_service_record.assets import AssetResolver        # noqa: E402
from korea_service_record.locate import find_game_dir        # noqa: E402

LANGS = ("eng", "ger", "fra", "spa", "rus", "chs")
LOCALE = "nsdata/assets/locale"
TEXTS = "nsdata/assets/awards/6xx"

DUC_NAMES = {
    "eng": "Distinguished Unit Citation",
    "ger": "Distinguished Unit Citation",
    "fra": "Distinguished Unit Citation",
    "spa": "Mención de Unidad Distinguida",
    "rus": "Благодарность отличившейся части",
    "chs": "杰出部队嘉奖",
}

DUC_DESCRIPTIONS = {
    "eng": """\
The Distinguished Unit Citation is awarded to a unit of the armed forces of the United States, and to co-belligerent units, for extraordinary heroism in action against an armed enemy. The degree of heroism required is the same as that which would warrant the Distinguished Service Cross for an individual: the unit must have performed with such gallantry, determination and esprit de corps, under extremely difficult and hazardous conditions, as to set it apart from other units taking part in the same campaign.

It was established by Executive Order in February 1942 as the Distinguished Unit Badge and renamed the following year. The emblem is a ribbon of Old Glory blue set in a frame of gold laurel leaves, worn on the right breast above the pocket rather than with the individual decorations on the left. Everyone assigned to the unit at the time of the cited action wears it permanently; those who join later wear it only for as long as they serve with the unit. In 1957 it was renamed the Presidential Unit Citation.

In Korea it went to a number of Fifth Air Force wings and groups. The 4th and 51st Fighter-Interceptor Wings were both cited for their fighting over MiG Alley, and fighter-bomber wings for the interdiction campaign against the roads and railways feeding the front.""",

    "ger": """\
Die Distinguished Unit Citation wird einem Verband der Streitkräfte der Vereinigten Staaten sowie verbündeten Verbänden für außerordentliche Tapferkeit im Gefecht gegen einen bewaffneten Feind verliehen. Das geforderte Maß entspricht dem, das einem Einzelnen das Distinguished Service Cross einbringen würde: Der Verband muss sich unter äußerst schwierigen und gefährlichen Bedingungen durch Tapferkeit, Entschlossenheit und Korpsgeist so hervorgetan haben, dass er sich von den übrigen am selben Feldzug beteiligten Verbänden abhebt.

Sie wurde im Februar 1942 durch Executive Order als Distinguished Unit Badge gestiftet und im Jahr darauf umbenannt. Das Abzeichen ist ein Band in Old-Glory-Blau in einem Rahmen aus goldenen Lorbeerblättern; es wird auf der rechten Brustseite über der Tasche getragen, getrennt von den persönlichen Auszeichnungen links. Wer dem Verband zur Zeit der gewürdigten Handlung angehörte, trägt es dauerhaft; später Hinzugekommene nur für die Dauer ihrer Zugehörigkeit. 1957 wurde sie in Presidential Unit Citation umbenannt.

In Korea erhielten sie mehrere Geschwader und Gruppen der Fifth Air Force. Das 4th und das 51st Fighter-Interceptor Wing wurden für ihre Kämpfe über der MiG Alley ausgezeichnet, Jagdbombergeschwader für den Interdiktionsfeldzug gegen die Straßen und Bahnlinien, die die Front versorgten.""",

    "fra": """\
La Distinguished Unit Citation est décernée à une unité des forces armées des États-Unis, ainsi qu'aux unités alliées, pour un héroïsme extraordinaire au combat face à un ennemi armé. Le degré d'héroïsme exigé est celui qui vaudrait la Distinguished Service Cross à un individu : l'unité doit avoir fait preuve, dans des conditions extrêmement difficiles et périlleuses, d'une bravoure, d'une détermination et d'un esprit de corps tels qu'elle se distingue des autres unités engagées dans la même campagne.

Créée par décret présidentiel en février 1942 sous le nom de Distinguished Unit Badge, elle est rebaptisée l'année suivante. L'insigne est un ruban bleu « Old Glory » serti dans un cadre de feuilles de laurier dorées, porté sur la poitrine droite, au-dessus de la poche, à l'écart des décorations individuelles portées à gauche. Ceux qui appartenaient à l'unité lors de l'action citée le portent à titre permanent ; ceux qui la rejoignent ensuite, seulement tant qu'ils y servent. En 1957, elle devient la Presidential Unit Citation.

En Corée, elle fut attribuée à plusieurs escadres et groupes de la Fifth Air Force. Les 4th et 51st Fighter-Interceptor Wings furent cités pour leurs combats au-dessus de la MiG Alley, et des escadres de chasseurs-bombardiers pour la campagne d'interdiction contre les routes et voies ferrées ravitaillant le front.""",

    "spa": """\
La Mención de Unidad Distinguida se concede a una unidad de las fuerzas armadas de los Estados Unidos, y a unidades cobeligerantes, por heroísmo extraordinario en acción contra un enemigo armado. El grado de heroísmo exigido es el mismo que valdría a un individuo la Distinguished Service Cross: la unidad debe haber actuado, en condiciones extremadamente difíciles y peligrosas, con tal valor, determinación y espíritu de cuerpo que se distinga de las demás unidades que tomaron parte en la misma campaña.

Fue instituida por orden ejecutiva en febrero de 1942 como Distinguished Unit Badge y renombrada al año siguiente. El emblema es una cinta azul «Old Glory» engastada en un marco de hojas de laurel doradas, que se lleva en el lado derecho del pecho, sobre el bolsillo, separada de las condecoraciones individuales del lado izquierdo. Quienes pertenecían a la unidad en el momento de la acción citada la llevan de forma permanente; quienes se incorporan después, solo mientras sirven en ella. En 1957 pasó a llamarse Presidential Unit Citation.

En Corea la recibieron varias alas y grupos de la Fifth Air Force. Las 4th y 51st Fighter-Interceptor Wings fueron citadas por sus combates sobre el Callejón de los MiG, y las alas de cazabombarderos por la campaña de interdicción contra las carreteras y ferrocarriles que abastecían el frente.""",

    "rus": """\
Благодарность отличившейся части присуждается части вооружённых сил США, а также союзным частям, за исключительный героизм в бою с вооружённым противником. Требуемая степень героизма та же, за которую отдельному военнослужащему полагался бы Крест «За выдающиеся заслуги»: часть должна проявить в крайне тяжёлых и опасных условиях такую отвагу, решимость и боевой дух, чтобы выделиться среди других частей, участвовавших в той же кампании.

Учреждена указом президента в феврале 1942 года как Distinguished Unit Badge и переименована на следующий год. Знак представляет собой ленту синего цвета «Олд Глори» в рамке из золотых лавровых листьев; носится на правой стороне груди над карманом, отдельно от личных наград слева. Служившие в части на момент отмеченных действий носят его постоянно; пришедшие позже — лишь пока служат в этой части. В 1957 году переименована в Presidential Unit Citation.

В Корее её получили несколько авиакрыльев и групп Пятой воздушной армии. 4-е и 51-е истребительно-перехватывающие авиакрылья были отмечены за бои над «Аллеей МиГов», а истребительно-бомбардировочные авиакрылья — за кампанию по изоляции района боевых действий, удары по дорогам и железным дорогам, питавшим фронт.""",

    "chs": """\
杰出部队嘉奖授予美国武装部队及协同作战的盟军部队，以表彰其在对武装敌人的作战中表现出的非凡英勇。所要求的英勇程度与个人获授杰出服役十字勋章的标准相同：该部队必须在极其艰难和危险的条件下，以其英勇、决心和团队精神脱颖而出，有别于参加同一战役的其他部队。

该奖项于1942年2月依据总统行政命令设立，原名杰出部队徽章，次年更名。其标志为一条"老光荣"蓝色绶带，镶嵌于金色月桂叶框架之中，佩戴于右胸口袋上方，与佩戴于左胸的个人勋章分开。在受表彰行动发生时隶属该部队的人员可永久佩戴；此后加入者仅在该部队服役期间佩戴。1957年，该奖项更名为总统部队嘉奖。

在朝鲜战争中，第五航空队的多个联队和大队获得此奖。第4和第51战斗截击联队因在"米格走廊"上空的战斗而受到嘉奖，战斗轰炸机联队则因对补给前线的公路和铁路实施的阻断作战而受到表彰。""",
}

# The Korean name is the one on the citation itself; the Western files keep
# the English form, as they do for the other American unit award.
ROK_NAMES = {
    "eng": "Republic of Korea Presidential Unit Citation",
    "ger": "Republic of Korea Presidential Unit Citation",
    "fra": "Republic of Korea Presidential Unit Citation",
    "spa": "Mención Presidencial de Unidad de la República de Corea",
    "rus": "Благодарность президента Республики Корея части",
    "chs": "大韩民国总统部队嘉奖",
}

ROK_DESCRIPTIONS = {
    "eng": """\
The Republic of Korea Presidential Unit Citation is conferred by the President of the Republic of Korea on a unit, not a person, for outstanding service in the defence of Korea. Where the Distinguished Unit Citation recognises a single action of extraordinary heroism, this one recognises the long haul: months of sustained operations that made a difference to the survival of the Republic.

The emblem is a ribbon of white grosgrain bearing the taegeuk, the red and blue whorl of the Korean flag, between edges of dark green set off by narrow stripes of red and white, worn in the same gold laurel frame as the American unit awards. American regulations allow every member of a cited unit to wear it permanently, and it is one of the most familiar ribbons on the chest of a Korean War veteran.

Syngman Rhee's government gave it generously to the United Nations forces. Almost every wing of the Fifth Air Force received it, as did the Far East Air Forces as a whole, the 1st Marine Aircraft Wing, most of the Navy's carrier air groups and the contingents of the other nations that fought under the UN flag.""",

    "ger": """\
Die Republic of Korea Presidential Unit Citation wird vom Präsidenten der Republik Korea einem Verband – nicht einer Person – für herausragende Verdienste bei der Verteidigung Koreas verliehen. Während die Distinguished Unit Citation eine einzelne Tat außerordentlicher Tapferkeit würdigt, würdigt diese den langen Weg: Monate ununterbrochener Einsätze, die für das Überleben der Republik den Unterschied machten.

Das Abzeichen ist ein weißes Ripsband mit dem Taegeuk, dem rot-blauen Wirbel der koreanischen Flagge, zwischen dunkelgrünen Rändern, die von schmalen roten und weißen Streifen abgesetzt sind; getragen wird es im selben goldenen Lorbeerrahmen wie die amerikanischen Verbandsauszeichnungen. Nach amerikanischen Vorschriften darf jedes Mitglied eines ausgezeichneten Verbands es dauerhaft tragen, und es ist eines der vertrautesten Bänder auf der Brust eines Koreakriegsveteranen.

Die Regierung Syngman Rhees vergab sie großzügig an die Streitkräfte der Vereinten Nationen. Fast jedes Geschwader der Fifth Air Force erhielt sie, ebenso die Far East Air Forces als Ganzes, das 1st Marine Aircraft Wing, die meisten Trägergeschwader der Navy und die Kontingente der übrigen Nationen, die unter der UN-Flagge kämpften.""",

    "fra": """\
La Republic of Korea Presidential Unit Citation est conférée par le président de la République de Corée à une unité, et non à une personne, pour services exceptionnels dans la défense de la Corée. Là où la Distinguished Unit Citation récompense une action isolée d'héroïsme extraordinaire, celle-ci récompense la durée : des mois d'opérations soutenues qui ont pesé sur la survie de la République.

L'insigne est un ruban de gros-grain blanc portant le taegeuk, le tourbillon rouge et bleu du drapeau coréen, entre des bords vert foncé rehaussés d'étroites rayures rouges et blanches, porté dans le même cadre de laurier doré que les récompenses collectives américaines. Le règlement américain autorise chaque membre d'une unité citée à le porter à titre permanent, et c'est l'un des rubans les plus familiers sur la poitrine d'un vétéran de Corée.

Le gouvernement de Syngman Rhee l'accorda généreusement aux forces des Nations unies. Presque toutes les escadres de la Fifth Air Force la reçurent, de même que les Far East Air Forces dans leur ensemble, la 1st Marine Aircraft Wing, la plupart des groupes aériens embarqués de la Navy et les contingents des autres nations engagées sous le drapeau de l'ONU.""",

    "spa": """\
La Mención Presidencial de Unidad de la República de Corea es conferida por el presidente de la República de Corea a una unidad, no a una persona, por servicios sobresalientes en la defensa de Corea. Mientras la Mención de Unidad Distinguida reconoce una sola acción de heroísmo extraordinario, esta reconoce la larga travesía: meses de operaciones sostenidas que resultaron decisivos para la supervivencia de la República.

El emblema es una cinta de gros blanco con el taegeuk, el remolino rojo y azul de la bandera coreana, entre bordes verde oscuro realzados por estrechas franjas rojas y blancas, llevada en el mismo marco de laurel dorado que las condecoraciones de unidad estadounidenses. El reglamento estadounidense permite a todos los miembros de una unidad citada llevarla de forma permanente, y es una de las cintas más familiares en el pecho de un veterano de Corea.

El gobierno de Syngman Rhee la otorgó con generosidad a las fuerzas de las Naciones Unidas. Casi todas las alas de la Fifth Air Force la recibieron, al igual que las Far East Air Forces en su conjunto, la 1st Marine Aircraft Wing, la mayoría de los grupos aéreos embarcados de la Navy y los contingentes de las demás naciones que combatieron bajo la bandera de la ONU.""",

    "rus": """\
Благодарность президента Республики Корея части объявляется президентом Республики Корея части, а не отдельному лицу, за выдающиеся заслуги в обороне Кореи. Если Благодарность отличившейся части отмечает одно действие исключительного героизма, то эта отмечает долгий путь: месяцы непрерывных боевых действий, которые повлияли на само выживание Республики.

Знак представляет собой белую репсовую ленту с тхэгыком — красно-синим вихрем корейского флага — между тёмно-зелёными краями, оттенёнными узкими красными и белыми полосками; носится в той же рамке из золотых лавровых листьев, что и американские коллективные награды. Американские правила разрешают каждому военнослужащему отмеченной части носить её постоянно, и это одна из самых узнаваемых лент на груди ветерана Корейской войны.

Правительство Ли Сын Мана щедро жаловало её силам Организации Объединённых Наций. Её получили почти все авиакрылья Пятой воздушной армии, Дальневосточные ВВС в целом, 1-е авиакрыло морской пехоты, большинство палубных авиагрупп флота и контингенты других стран, воевавших под флагом ООН.""",

    "chs": """\
大韩民国总统部队嘉奖由大韩民国总统授予部队而非个人，以表彰其在保卫韩国中的卓越贡献。杰出部队嘉奖表彰的是一次非凡英勇的行动，而此奖表彰的是长期坚持：数月持续不断的作战行动，对共和国的存亡起到了决定性作用。

其标志为一条白色罗纹绶带，中央饰以太极——韩国国旗上的红蓝旋纹——两侧为深绿色边缘，并以细窄的红白条纹相衬，佩戴于与美国部队奖项相同的金色月桂叶框架之中。根据美国条例，受表彰部队的每一名成员均可永久佩戴，它是朝鲜战争老兵胸前最为常见的绶带之一。

李承晚政府将此奖慷慨授予联合国军。第五航空队几乎所有联队均获此奖，远东航空军整体、第1陆战队航空联队、海军大多数舰载航空大队以及在联合国旗帜下作战的其他国家的部队亦获此殊荣。""",
}

# A second DUC is worn as a bronze oak leaf cluster on the first; the names
# follow each file's wording for the Medal of Honor cluster (award601041).
DUC2_NAMES = {
    "eng": "Bronze Oak Leaf Cluster in Lieu of 2nd Distinguished Unit Citation",
    "ger": "Distinguished Unit Citation (erstes Eichenlaub)",
    "fra": "Distinguished Unit Citation (1re agrafe feuille de chêne bronze)",
    "spa": "Mención de Unidad Distinguida (Primer Racimo de Hojas de Roble)",
    "rus": "Благодарность отличившейся части с одним бронзовым дубовым листом",
    "chs": "杰出部队嘉奖（第一枚橡叶簇）",
}

DUC2_DESCRIPTIONS = {
    "eng": """\
A unit cited a second time does not receive a second emblem. In the American system a further award of the same decoration is shown by a device on the first, and for the Distinguished Unit Citation that device is a bronze oak leaf cluster, a small sprig of leaves and acorns pinned to the centre of the blue ribbon inside its gold frame.

Each cluster stands for one further citation, and every member serving with the unit at the time of the second action wears it permanently, just as with the first. The standard is unchanged: extraordinary heroism in action against an armed enemy, of the degree that would earn an individual the Distinguished Service Cross.

Several Fifth Air Force wings were cited more than once in Korea. The 4th Fighter-Interceptor Wing, the most successful of the Sabre wings, was cited twice for its fighting over MiG Alley, and fighter-bomber and light-bomber wings collected further citations through the long interdiction campaign.""",

    "ger": """\
Ein zum zweiten Mal ausgezeichneter Verband erhält kein zweites Abzeichen. Im amerikanischen System wird eine weitere Verleihung derselben Auszeichnung durch eine Auflage auf der ersten kenntlich gemacht; bei der Distinguished Unit Citation ist das ein bronzenes Eichenlaub, ein kleiner Zweig aus Blättern und Eicheln, der in die Mitte des blauen Bandes im goldenen Rahmen gesteckt wird.

Jedes Eichenlaub steht für eine weitere Würdigung, und wer dem Verband zur Zeit der zweiten Handlung angehörte, trägt es dauerhaft, genau wie beim ersten Mal. Der Maßstab bleibt derselbe: außerordentliche Tapferkeit im Gefecht gegen einen bewaffneten Feind in dem Maß, das einem Einzelnen das Distinguished Service Cross einbrächte.

Mehrere Geschwader der Fifth Air Force wurden in Korea mehr als einmal gewürdigt. Das 4th Fighter-Interceptor Wing, das erfolgreichste der Sabre-Geschwader, wurde zweimal für seine Kämpfe über der MiG Alley ausgezeichnet, und Jagdbomber- und leichte Bombergeschwader sammelten im langen Interdiktionsfeldzug weitere Würdigungen.""",

    "fra": """\
Une unité citée une seconde fois ne reçoit pas un second insigne. Dans le système américain, une nouvelle attribution de la même décoration est marquée par un dispositif fixé sur la première ; pour la Distinguished Unit Citation, ce dispositif est une agrafe en feuille de chêne bronze, un petit rameau de feuilles et de glands épinglé au centre du ruban bleu dans son cadre doré.

Chaque agrafe représente une citation supplémentaire, et tout membre servant dans l'unité au moment de la seconde action la porte à titre permanent, comme pour la première. Le critère est inchangé : un héroïsme extraordinaire au combat face à un ennemi armé, du degré qui vaudrait la Distinguished Service Cross à un individu.

Plusieurs escadres de la Fifth Air Force furent citées plus d'une fois en Corée. La 4th Fighter-Interceptor Wing, la plus brillante des escadres de Sabre, fut citée deux fois pour ses combats au-dessus de la MiG Alley, et les escadres de chasseurs-bombardiers et de bombardiers légers accumulèrent d'autres citations au long de la campagne d'interdiction.""",

    "spa": """\
Una unidad citada por segunda vez no recibe un segundo emblema. En el sistema estadounidense, una nueva concesión de la misma condecoración se indica con un distintivo sobre la primera; para la Mención de Unidad Distinguida ese distintivo es un racimo de hojas de roble de bronce, una pequeña rama de hojas y bellotas prendida en el centro de la cinta azul dentro de su marco dorado.

Cada racimo representa una mención adicional, y todo miembro que sirviera en la unidad en el momento de la segunda acción lo lleva de forma permanente, igual que con la primera. El criterio no cambia: heroísmo extraordinario en acción contra un enemigo armado, del grado que valdría a un individuo la Distinguished Service Cross.

Varias alas de la Fifth Air Force fueron citadas más de una vez en Corea. La 4th Fighter-Interceptor Wing, la más exitosa de las alas de Sabre, fue citada dos veces por sus combates sobre el Callejón de los MiG, y las alas de cazabombarderos y de bombarderos ligeros acumularon nuevas menciones a lo largo de la campaña de interdicción.""",

    "rus": """\
Часть, отмеченная во второй раз, не получает второго знака. В американской системе повторное награждение той же наградой обозначается знаком на первой; для Благодарности отличившейся части это бронзовый дубовый лист — маленькая веточка с листьями и желудями, прикреплённая в центре синей ленты в золотой рамке.

Каждый лист означает ещё одну благодарность, и каждый, кто служил в части на момент второго отмеченного действия, носит его постоянно, как и первый. Требование прежнее: исключительный героизм в бою с вооружённым противником — той степени, за которую отдельному военнослужащему полагался бы Крест «За выдающиеся заслуги».

Несколько авиакрыльев Пятой воздушной армии были отмечены в Корее более одного раза. 4-е истребительно-перехватывающее авиакрыло, самое результативное среди крыльев «Сейбров», дважды удостоилось благодарности за бои над «Аллеей МиГов», а истребительно-бомбардировочные и лёгкие бомбардировочные авиакрылья получали новые благодарности в ходе долгой кампании по изоляции района боевых действий.""",

    "chs": """\
部队第二次受到嘉奖时不会获得第二枚标志。在美国的制度中，同一奖项的再次授予以佩戴于首枚标志上的附件表示；对于杰出部队嘉奖而言，这一附件是一枚青铜橡叶簇——一小枝带有叶片和橡果的饰物，别在金色框架内蓝色绶带的中央。

每一枚橡叶簇代表一次额外的嘉奖，在第二次受表彰行动发生时隶属该部队的每一名成员均可永久佩戴，与首次嘉奖相同。标准保持不变：在对武装敌人的作战中表现出非凡英勇，其程度相当于个人获授杰出服役十字勋章。

第五航空队的多个联队在朝鲜战争中不止一次受到嘉奖。第4战斗截击联队是佩刀联队中战绩最为卓著的一个，因在"米格走廊"上空的战斗两次受到嘉奖；战斗轰炸机联队和轻型轰炸机联队则在漫长的阻断作战中屡获嘉奖。""",
}

# (award id, inserted after, names, descriptions) — order matters for the
# textual JSON insert, each after its predecessor.
AWARDS = (
    ("601042", "601041", DUC_NAMES, DUC_DESCRIPTIONS),
    ("601043", "601042", ROK_NAMES, ROK_DESCRIPTIONS),
    ("601044", "601043", DUC2_NAMES, DUC2_DESCRIPTIONS),
)


def set_or_insert_name(text: str, lang: str, award: str, after: str,
                       names: dict) -> str:
    key, value = f"award{award}", json.dumps(names[lang], ensure_ascii=False)
    line = re.compile(rf'^([ \t]*"{key}"\s*:\s*)"[^"]*"', re.M)
    if line.search(text):
        return line.sub(lambda m: m.group(1) + value, text, count=1)
    anchor = re.search(rf'^([ \t]*)"award{after}"\s*:\s*"[^"]*"(,?)', text, re.M)
    if not anchor:
        raise SystemExit(f"{lang}: no award{after} line to insert after")
    indent, comma = anchor.group(1), anchor.group(2)
    newline = "\r\n" if "\r\n" in text else "\n"
    head = text[:anchor.end()] + ("" if comma else ",")
    added = f'{newline}{indent}"{key}": {value}{"," if comma else ""}'
    return head + added + text[anchor.end():]


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

    for lang in LANGS:
        # -- names -----------------------------------------------------
        vpath = f"{LOCALE}/awards.locale={lang}.json"
        original = res.read(vpath)
        if original is None:
            print(f"  {lang}: {vpath} not found, skipped")
            continue
        text = original.decode("utf-8")           # bytes, so CRLF survives
        patched = text
        for award, after, names, _ in AWARDS:
            patched = set_or_insert_name(patched, lang, award, after, names)
        json.loads(patched)                       # refuse to write invalid JSON
        name_changed = patched != text

        # -- descriptions ----------------------------------------------
        pending = []
        for award, _, _, descriptions in AWARDS:
            body = descriptions[lang].replace("\n", "\r\n").encode("utf-8")
            tpath = data / Path(TEXTS) / f"{award}.locale={lang}.txt"
            if not tpath.is_file() or tpath.read_bytes() != body:
                pending.append((award, tpath, body))

        state = []
        if name_changed:
            state.append("names -> " + ", ".join(n[lang] for _, _, n, _ in AWARDS))
        for award, _, body in pending:
            state.append(f"{award} description {len(body):,} bytes")
        print(f"  {lang}: {'; '.join(state) or 'complete already'}")
        if args.dry_run:
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
