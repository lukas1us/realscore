"""
Číselník českých krajů a měst.
Používá se pro přiřazení kraje nemovitosti při ukládání do DB.
"""

CZECH_REGIONS: list[str] = [
    "Hlavní město Praha",
    "Středočeský kraj",
    "Jihočeský kraj",
    "Plzeňský kraj",
    "Karlovarský kraj",
    "Ústecký kraj",
    "Liberecký kraj",
    "Královéhradecký kraj",
    "Pardubický kraj",
    "Kraj Vysočina",
    "Jihomoravský kraj",
    "Olomoucký kraj",
    "Zlínský kraj",
    "Moravskoslezský kraj",
]

# Mapping: název obce → kraj
CITY_TO_REGION: dict[str, str] = {
    # Hlavní město Praha
    "Praha": "Hlavní město Praha",
    # Středočeský kraj
    "Kladno": "Středočeský kraj", "Mladá Boleslav": "Středočeský kraj",
    "Příbram": "Středočeský kraj", "Kolín": "Středočeský kraj",
    "Kutná Hora": "Středočeský kraj", "Mělník": "Středočeský kraj",
    "Beroun": "Středočeský kraj", "Rakovník": "Středočeský kraj",
    "Benešov": "Středočeský kraj", "Nymburk": "Středočeský kraj",
    "Slaný": "Středočeský kraj", "Kralupy nad Vltavou": "Středočeský kraj",
    "Brandýs nad Labem-Stará Boleslav": "Středočeský kraj",
    "Brandýs nad Labem": "Středočeský kraj",
    "Neratovice": "Středočeský kraj", "Říčany": "Středočeský kraj",
    "Lysá nad Labem": "Středočeský kraj", "Poděbrady": "Středočeský kraj",
    "Vlašim": "Středočeský kraj", "Sedlčany": "Středočeský kraj",
    "Hořovice": "Středočeský kraj", "Dobříš": "Středočeský kraj",
    "Votice": "Středočeský kraj", "Mnichovo Hradiště": "Středočeský kraj",
    "Čelákovice": "Středočeský kraj", "Roztoky": "Středočeský kraj",
    "Černošice": "Středočeský kraj", "Jesenice": "Středočeský kraj",
    "Úvaly": "Středočeský kraj", "Benátky nad Jizerou": "Středočeský kraj",
    "Kostelec nad Černými lesy": "Středočeský kraj",
    "Mnichovice": "Středočeský kraj", "Čáslav": "Středočeský kraj",
    "Rudná": "Středočeský kraj", "Hostivice": "Středočeský kraj",
    "Průhonice": "Středočeský kraj", "Vestec": "Středočeský kraj",
    "Tuchoměřice": "Středočeský kraj", "Zlonice": "Středočeský kraj",
    "Unhošť": "Středočeský kraj", "Nučice": "Středočeský kraj",
    "Čerčany": "Středočeský kraj", "Pyšely": "Středočeský kraj",
    "Dobrovice": "Středočeský kraj", "Kosmonosy": "Středočeský kraj",
    "Milovice": "Středočeský kraj", "Zruč nad Sázavou": "Středočeský kraj",
    # Jihočeský kraj
    "České Budějovice": "Jihočeský kraj", "Písek": "Jihočeský kraj",
    "Tábor": "Jihočeský kraj", "Jindřichův Hradec": "Jihočeský kraj",
    "Strakonice": "Jihočeský kraj", "Prachatice": "Jihočeský kraj",
    "Kaplice": "Jihočeský kraj", "Třeboň": "Jihočeský kraj",
    "Soběslav": "Jihočeský kraj", "Blatná": "Jihočeský kraj",
    "Milevsko": "Jihočeský kraj", "Vodňany": "Jihočeský kraj",
    "Vimperk": "Jihočeský kraj", "Sezimovo Ústí": "Jihočeský kraj",
    "Planá nad Lužnicí": "Jihočeský kraj", "Český Krumlov": "Jihočeský kraj",
    "Veselí nad Lužnicí": "Jihočeský kraj", "Dačice": "Jihočeský kraj",
    "Týn nad Vltavou": "Jihočeský kraj", "Netolice": "Jihočeský kraj",
    # Plzeňský kraj
    "Plzeň": "Plzeňský kraj", "Klatovy": "Plzeňský kraj",
    "Rokycany": "Plzeňský kraj", "Domažlice": "Plzeňský kraj",
    "Tachov": "Plzeňský kraj", "Horažďovice": "Plzeňský kraj",
    "Nepomuk": "Plzeňský kraj", "Stříbro": "Plzeňský kraj",
    "Nýřany": "Plzeňský kraj", "Přeštice": "Plzeňský kraj",
    "Stod": "Plzeňský kraj", "Dobřany": "Plzeňský kraj",
    "Sušice": "Plzeňský kraj", "Kdyně": "Plzeňský kraj",
    # Karlovarský kraj
    "Karlovy Vary": "Karlovarský kraj", "Cheb": "Karlovarský kraj",
    "Sokolov": "Karlovarský kraj", "Mariánské Lázně": "Karlovarský kraj",
    "Ostrov": "Karlovarský kraj", "Aš": "Karlovarský kraj",
    "Kraslice": "Karlovarský kraj", "Chodov": "Karlovarský kraj",
    "Františkovy Lázně": "Karlovarský kraj", "Nejdek": "Karlovarský kraj",
    "Loket": "Karlovarský kraj", "Horní Slavkov": "Karlovarský kraj",
    # Ústecký kraj
    "Ústí nad Labem": "Ústecký kraj", "Most": "Ústecký kraj",
    "Chomutov": "Ústecký kraj", "Teplice": "Ústecký kraj",
    "Děčín": "Ústecký kraj", "Litoměřice": "Ústecký kraj",
    "Louny": "Ústecký kraj", "Roudnice nad Labem": "Ústecký kraj",
    "Bílina": "Ústecký kraj", "Duchcov": "Ústecký kraj",
    "Klášterec nad Ohří": "Ústecký kraj", "Litvínov": "Ústecký kraj",
    "Kadaň": "Ústecký kraj", "Jirkov": "Ústecký kraj",
    "Žatec": "Ústecký kraj", "Varnsdorf": "Ústecký kraj",
    "Rumburk": "Ústecký kraj", "Šluknov": "Ústecký kraj",
    "Lovosice": "Ústecký kraj", "Podbořany": "Ústecký kraj",
    "Krupka": "Ústecký kraj", "Česká Kamenice": "Ústecký kraj",
    # Liberecký kraj
    "Liberec": "Liberecký kraj", "Jablonec nad Nisou": "Liberecký kraj",
    "Česká Lípa": "Liberecký kraj", "Semily": "Liberecký kraj",
    "Frýdlant": "Liberecký kraj", "Tanvald": "Liberecký kraj",
    "Turnov": "Liberecký kraj", "Nový Bor": "Liberecký kraj",
    "Hrádek nad Nisou": "Liberecký kraj", "Jilemnice": "Liberecký kraj",
    "Lomnice nad Popelkou": "Liberecký kraj", "Železný Brod": "Liberecký kraj",
    "Chrastava": "Liberecký kraj", "Doksy": "Liberecký kraj",
    "Mimoň": "Liberecký kraj", "Stráž pod Ralskem": "Liberecký kraj",
    # Královéhradecký kraj
    "Hradec Králové": "Královéhradecký kraj", "Náchod": "Královéhradecký kraj",
    "Trutnov": "Královéhradecký kraj", "Jičín": "Královéhradecký kraj",
    "Rychnov nad Kněžnou": "Královéhradecký kraj",
    "Dvůr Králové nad Labem": "Královéhradecký kraj",
    "Jaroměř": "Královéhradecký kraj", "Nový Bydžov": "Královéhradecký kraj",
    "Hořice": "Královéhradecký kraj", "Broumov": "Královéhradecký kraj",
    "Vrchlabí": "Královéhradecký kraj", "Police nad Metují": "Královéhradecký kraj",
    "Nová Paka": "Královéhradecký kraj", "Dobruška": "Královéhradecký kraj",
    "Kostelec nad Orlicí": "Královéhradecký kraj",
    "Lázně Bělohrad": "Královéhradecký kraj", "Hostinné": "Královéhradecký kraj",
    "Špindlerův Mlýn": "Královéhradecký kraj",
    # Pardubický kraj
    "Pardubice": "Pardubický kraj", "Chrudim": "Pardubický kraj",
    "Svitavy": "Pardubický kraj", "Ústí nad Orlicí": "Pardubický kraj",
    "Hlinsko": "Pardubický kraj", "Polička": "Pardubický kraj",
    "Litomyšl": "Pardubický kraj", "Vysoké Mýto": "Pardubický kraj",
    "Lanškroun": "Pardubický kraj", "Žamberk": "Pardubický kraj",
    "Přelouč": "Pardubický kraj", "Heřmanův Městec": "Pardubický kraj",
    "Moravská Třebová": "Pardubický kraj", "Holice": "Pardubický kraj",
    "Česká Třebová": "Pardubický kraj", "Sezemice": "Pardubický kraj",
    # Kraj Vysočina
    "Jihlava": "Kraj Vysočina", "Havlíčkův Brod": "Kraj Vysočina",
    "Třebíč": "Kraj Vysočina", "Žďár nad Sázavou": "Kraj Vysočina",
    "Pelhřimov": "Kraj Vysočina", "Humpolec": "Kraj Vysočina",
    "Velké Meziříčí": "Kraj Vysočina", "Bystřice nad Pernštejnem": "Kraj Vysočina",
    "Světlá nad Sázavou": "Kraj Vysočina", "Ledeč nad Sázavou": "Kraj Vysočina",
    "Telč": "Kraj Vysočina", "Moravské Budějovice": "Kraj Vysočina",
    "Náměšť nad Oslavou": "Kraj Vysočina", "Chotěboř": "Kraj Vysočina",
    "Nové Město na Moravě": "Kraj Vysočina", "Velká Bíteš": "Kraj Vysočina",
    "Polná": "Kraj Vysočina", "Pacov": "Kraj Vysočina",
    # Jihomoravský kraj
    "Brno": "Jihomoravský kraj", "Znojmo": "Jihomoravský kraj",
    "Hodonín": "Jihomoravský kraj", "Břeclav": "Jihomoravský kraj",
    "Blansko": "Jihomoravský kraj", "Vyškov": "Jihomoravský kraj",
    "Boskovice": "Jihomoravský kraj", "Kyjov": "Jihomoravský kraj",
    "Hustopeče": "Jihomoravský kraj", "Mikulov": "Jihomoravský kraj",
    "Kuřim": "Jihomoravský kraj", "Šlapanice": "Jihomoravský kraj",
    "Modřice": "Jihomoravský kraj", "Slavkov u Brna": "Jihomoravský kraj",
    "Rosice": "Jihomoravský kraj", "Tišnov": "Jihomoravský kraj",
    "Veselí nad Moravou": "Jihomoravský kraj", "Strážnice": "Jihomoravský kraj",
    "Pohořelice": "Jihomoravský kraj", "Ivančice": "Jihomoravský kraj",
    "Adamov": "Jihomoravský kraj", "Letovice": "Jihomoravský kraj",
    "Valtice": "Jihomoravský kraj", "Lednice": "Jihomoravský kraj",
    "Rajhrad": "Jihomoravský kraj", "Zastávka": "Jihomoravský kraj",
    # Olomoucký kraj
    "Olomouc": "Olomoucký kraj", "Prostějov": "Olomoucký kraj",
    "Přerov": "Olomoucký kraj", "Šumperk": "Olomoucký kraj",
    "Jeseník": "Olomoucký kraj", "Uničov": "Olomoucký kraj",
    "Hranice": "Olomoucký kraj", "Litovel": "Olomoucký kraj",
    "Konice": "Olomoucký kraj", "Mohelnice": "Olomoucký kraj",
    "Zábřeh": "Olomoucký kraj", "Šternberk": "Olomoucký kraj",
    "Lipník nad Bečvou": "Olomoucký kraj", "Zlaté Hory": "Olomoucký kraj",
    "Hanušovice": "Olomoucký kraj", "Velká Bystřice": "Olomoucký kraj",
    # Zlínský kraj
    "Zlín": "Zlínský kraj", "Uherské Hradiště": "Zlínský kraj",
    "Vsetín": "Zlínský kraj", "Kroměříž": "Zlínský kraj",
    "Otrokovice": "Zlínský kraj", "Uherský Brod": "Zlínský kraj",
    "Vizovice": "Zlínský kraj", "Holešov": "Zlínský kraj",
    "Bystřice pod Hostýnem": "Zlínský kraj", "Luhačovice": "Zlínský kraj",
    "Valašské Meziříčí": "Zlínský kraj", "Rožnov pod Radhoštěm": "Zlínský kraj",
    "Valašské Klobouky": "Zlínský kraj", "Slavičín": "Zlínský kraj",
    "Napajedla": "Zlínský kraj", "Kunovice": "Zlínský kraj",
    "Staré Město": "Zlínský kraj", "Hulín": "Zlínský kraj",
    # Moravskoslezský kraj
    "Ostrava": "Moravskoslezský kraj", "Opava": "Moravskoslezský kraj",
    "Frýdek-Místek": "Moravskoslezský kraj", "Karviná": "Moravskoslezský kraj",
    "Havířov": "Moravskoslezský kraj", "Orlová": "Moravskoslezský kraj",
    "Bohumín": "Moravskoslezský kraj", "Nový Jičín": "Moravskoslezský kraj",
    "Třinec": "Moravskoslezský kraj", "Kopřivnice": "Moravskoslezský kraj",
    "Frýdlant nad Ostravicí": "Moravskoslezský kraj",
    "Bruntál": "Moravskoslezský kraj", "Krnov": "Moravskoslezský kraj",
    "Frenštát pod Radhoštěm": "Moravskoslezský kraj",
    "Hlučín": "Moravskoslezský kraj", "Český Těšín": "Moravskoslezský kraj",
    "Bílovec": "Moravskoslezský kraj", "Odry": "Moravskoslezský kraj",
    "Rýmařov": "Moravskoslezský kraj", "Příbor": "Moravskoslezský kraj",
    "Studénka": "Moravskoslezský kraj", "Klimkovice": "Moravskoslezský kraj",
    "Petřvald": "Moravskoslezský kraj", "Rychvald": "Moravskoslezský kraj",
    "Fulnek": "Moravskoslezský kraj", "Jablunkov": "Moravskoslezský kraj",
}

# Odvozená mapa: kraj → seznam měst (pro zpětné dohledání)
REGION_TO_CITIES: dict[str, list[str]] = {r: [] for r in CZECH_REGIONS}
for _city, _region in CITY_TO_REGION.items():
    if _region in REGION_TO_CITIES:
        REGION_TO_CITIES[_region].append(_city)


def city_to_kraj(city: str | None) -> str | None:
    """Vrátí název kraje pro dané město, nebo None pokud město není v mapě."""
    if not city:
        return None
    return CITY_TO_REGION.get(city)


def extract_kraj(city: str | None, district: str | None) -> str | None:
    """
    Pokusí se určit kraj z dostupných lokačních polí.

    Sreality ukládá data jako 'Ulice, Město' — tedy:
      city     = název ulice (nebo obec, pokud je jediný prvek)
      district = název obce / čtvrti

    Strategie (v pořadí):
    1. city odpovídá klíči v mapě → přímý lookup
    2. city začíná 'Praha' (vč. 'Praha 9', 'Praha 6 - Břevnov') → Praha
    3. district odpovídá klíči v mapě → přímý lookup
    4. district začíná 'Praha' → Praha
    5. district ve tvaru 'okres Xxx' → lookup na 'Xxx'
    """
    import re

    if city:
        if re.match(r"^Praha\b", city, re.IGNORECASE):
            return "Hlavní město Praha"
        result = CITY_TO_REGION.get(city)
        if result:
            return result

    if district:
        if re.match(r"^Praha\b", district, re.IGNORECASE):
            return "Hlavní město Praha"
        # Přímý lookup na district
        result = CITY_TO_REGION.get(district)
        if result:
            return result
        # "Brno - Žebětín", "Olomouc - Povel" → vezmi část před " - "
        base = district.split(" - ")[0].strip()
        if base != district:
            if re.match(r"^Praha\b", base, re.IGNORECASE):
                return "Hlavní město Praha"
            result = CITY_TO_REGION.get(base)
            if result:
                return result
        # "okres Prachatice" → "Prachatice"
        stripped = re.sub(r"^okres\s+", "", district, flags=re.IGNORECASE).strip()
        result = CITY_TO_REGION.get(stripped)
        if result:
            return result

    return None
