#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MEO EPG: guarda XMLs datados intactos e combina todos num unico XMLTV .xml.gz.
Sem dependencias externas; suporta menu local e execucao automatica no GitHub Actions.
"""
import gzip
import tarfile
import json
import logging
import os
import re
import ssl
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

NR_DAYS_PAST = 7
NR_DAYS_FUTURE = 7
REQUEST_TIMEOUT = 20
OUTPUT_GZ = 'epg_meogo.xml.gz'
BASE_URL = 'https://www.meo.pt'
# CallLetter MEO -> tvg-id usado na lista M3U
MEO_TO_TVG = {
'RTP1': 'RTP1.pt', 'RTP2': 'RTP2.pt', 'SIC': 'SIC.pt', 'TVI': 'TVI.pt', 'SICN': 'SICNoticias.pt', 'RTPN': 'RTPNoticias.pt', 'CNNPT': 'CNNPortugal.pt', 'CMTV': 'CMTV.pt', 'NEWSNOW': 'NewsNow.pt', 'GLOB': 'Globo.pt', 'C11': 'Canal11.pt', 'VMAISTVI': 'VPlusTVI.pt', 'PORTO': 'PortoCanal.pt', 'SICC': 'SICCaras.pt', 'SICR': 'SICRadical.pt', 'SICM': 'SICMulher.pt', 'SICNOV': 'SICNovelas.pt', 'RTPM': 'RTPMemoria.pt', 'SPTVHD': 'SportTVPlus.pt', 'SPT1HD': 'SportTV1.pt', 'SPT2HD': 'SportTV2.pt', 'SPT3HD': 'SportTV3.pt', 'SPT4HD': 'SportTV4.pt', 'SPT5HD': 'SportTV5.pt', 'SPT6HD': 'SportTV6.pt', 'SPT7HD': 'SportTV7.pt', 'EURHD': 'Eurosport1.pt', 'EURS2HD': 'Eurosport2.pt', 'ABOLA': 'ABolaTV.pt', 'SLBHD': 'BenficaTV.pt', 'SCPHD': 'SportingTV.pt', 'DAZN1': 'DAZN1.pt', 'DAZN2': 'DAZN2.pt', 'DAZN3': 'DAZN3.pt', 'DAZN4': 'DAZN4.pt', 'DAZN5': 'DAZN5.pt', 'DISNY': 'DisneyChannel.pt', 'DISNYJ': 'DisneyJunior.pt', 'PANDAK': 'PandaKids.pt', 'CART': 'CartoonNetwork.pt', 'PANDA': 'CanalPanda.pt', 'BABYT': 'BabyTV.uk', 'SICK': 'SICK.pt', 'NICKELO': 'Nickelodeon.pt', 'DIZI': 'TimelessDiziChannel.ro', 'TVCTOPH': 'TVCineTop.pt', 'TVCEDIH': 'TVCineEdition.pt', 'TVCEMOH': 'TVCineEmotion.pt', 'TVCACTH': 'TVCineAction.pt', 'HOLHD': 'CanalHollywood.pt', 'CINEHD': 'CineMundo.pt', 'STARMOV': 'StarMovies.pt', 'STARCHA': 'StarChannel.pt', 'AXNHD': 'AXN.pt', 'STARLIF': 'StarLife.pt', 'STARCRI': 'StarCrime.pt', 'STARCOM': 'StarComedy.pt', 'AXWHD': 'AXNWhite.pt', 'AXNMHD': 'AXNMovies.pt', 'SYFHD': 'Syfy.pt', 'AMCHD': 'AMC.pt', 'QHD': 'CanalQ.pt', 'MCMTHD': 'MCMTop.fr', 'MCM P': 'MCMPop.fr', 'AFRO': 'AfroMusic.pt', 'MEZHD': 'MezzoLive.fr', '24KTHD': '24Kitchen.pt', 'CASACOZ': 'CasaeCozinha.pt', 'DISCVHD': 'DiscoveryChannel.pt', 'NGHD': 'NationalGeographic.pt', 'WILDHD': 'NationalGeographicWild.pt', 'HISTHD': 'Historia.pt', 'ODISSHD': 'Odisseia.pt', 'AMCCRI': 'AMCCrime.pt', 'SMAISHD': 'SPlus.pt', 'TVIR': 'TVIReality.pt', 'REC HD': 'RecordTVEuropa.pt', 'AMCBRE': 'AMCBreak.pt', 'TLC': 'TLC.pt', 'FTVHD': 'FashionTVEurope.fr', 'GAMET': 'Gametoon.nl', 'ARTV': 'ARTV.pt', 'RECNEW': 'recordnews.pt', 'CNN': 'CNNInternational.us', 'EURN': 'EuronewsPortuguese.fr', 'BLOOM': 'BloombergTV.us', 'SKYN': 'SkyNewsInternational.uk', 'CNBC': 'CNBC.pt', 'ALJAZHD': 'AlJazeera.qa', 'TVE24HD': 'TVE24h.pt', 'FR24F': 'France24French.fr', 'FR24I': 'France24Espanol.fr', 'RTPMA': 'RTPMadeira.pt', 'RTPACR': 'RTPAcores.pt', 'LVTVHD': 'LocalVisaoTV.pt', 'RTPA': 'RTPAfrica.pt', 'TPA': 'TPA.ao', 'TVGAL': 'GaliciaTVEuropa.es', 'TVEIHD': 'TVEi.pt', 'TV5HD': 'TV5Monde.fr', 'RAI1': 'rai1.it', 'KBS': 'KBSWorld.kr', 'ARIRANG': 'ArirangTv.kr', 'NHKHD': 'NHKWorldJapan.jp', 'FREEDOM': 'Freedom.ua', 'CNOVA': 'TVCancaoNova.pt', 'UNIFE': 'UniFe.pt', 'KURIAKO': 'KuriakosTV.pt'
}
# IDs adicionais fornecidos em codigos_EPG_meogo.txt.
# Para os novos canais, o tvg-id XMLTV é a CallLetter MEO.
# Os mapeamentos existentes acima são mantidos sem alterações.
MEO_TO_TVG.update({
    'RTP3': 'RTP3',
    '18': '18',
    'WSPORT': 'WSPORT',
    'CNITO': 'CNITO',
    'NICKJR': 'NICKJR',
    'LOLLY': 'LOLLY',
    'KANUCA': 'KANUCA',
    'VOD': 'VOD',
    'VINTV': 'VINTV',
    'DEST': 'DEST',
    'MTVPHD': 'MTVPHD',
    'FIGHTSP': 'FIGHTSP',
    'NBATVHD': 'NBATVHD',
    'ID': 'ID',
    'GALERIA': 'GALERIA',
    'E! HD': 'E! HD',
    'TRAXP': 'TRAXP',
    'HGTV': 'HGTV',
    'MTV00S': 'MTV00S',
    'MTVLIVE': 'MTVLIVE',
    'TRAHD': 'TRAHD',
    'TRACETC': 'TRACETC',
    'TRACEBR': 'TRACEBR',
    'ALMALUS': 'ALMALUS',
    'BOMSOM': 'BOMSOM',
    'MEZZO': 'MEZZO',
    'CLASSIC': 'CLASSIC',
    'DJAZZ': 'DJAZZ',
    'ICOHD': 'ICOHD',
    'LOUD': 'LOUD',
    'RETRO': 'RETRO',
    'CONECTV': 'CONECTV',
    'AZORES': 'AZORES',
    'CAÇAPHD': 'CAÇAPHD',
    'CAÇAVHD': 'CAÇAVHD',
    'ONETORO': 'ONETORO',
    'DOGTVHD': 'DOGTVHD',
    'C180': 'C180',
    'TVVERHD': 'TVVERHD',
    'UME': 'UME',
    'NOVOT': 'NOVOT',
    'MAANAIM': 'MAANAIM',
    'DAYSTAI': 'DAYSTAI',
    'DAYSTAE': 'DAYSTAE',
    'GNEWS': 'GNEWS',
    'NEWBR': 'NEWBR',
    'TVA': 'TVA',
    'TCV': 'TCV',
    'ENGLISH': 'ENGLISH',
    'I24I': 'I24I',
    'CGTNHD': 'CGTNHD',
    'CGTNDHD': 'CGTNDHD',
    'EURNIHD': 'EURNIHD',
    'TRTWHD': 'TRTWHD',
    'RUSSTHD': 'RUSSTHD',
    '1RUSS': '1RUSS',
    'TELESUR': 'TELESUR',
    'CUBAV': 'CUBAV',
    'BFM': 'BFM',
    'BFMB': 'BFMB',
    'I24F': 'I24F',
    'FR2HD': 'FR2HD',
    'FR3HD': 'FR3HD',
    'FR4HD': 'FR4HD',
    'FR5HD': 'FR5HD',
    'FRINFO': 'FRINFO',
    'ARTEHD': 'ARTEHD',
    'EURNA': 'EURNA',
    'ARD': 'ARD',
    'ZDF': 'ZDF',
    'ZDFNEO': 'ZDFNEO',
    '3SAT': '3SAT',
    'KIKA': 'KIKA',
    'TAGES24': 'TAGES24',
    'BVN': 'BVN',
    'PROTV': 'PROTV',
    'BNT4': 'BNT4',
    'CCTV4HD': 'CCTV4HD',
    'PHCNE': 'PHCNE',
    '1E1INT': '1E1INT',
    '1E1UNEW': '1E1UNEW',
    'KVARTV': 'KVARTV',
    'STARCIN': 'STARCIN',
    'STARFAM': 'STARFAM',
    'XSPORT': 'XSPORT',
    'ITALIA': 'ITALIA',
    'RAI2': 'RAI2',
    'RAI3': 'RAI3',
    'RAINEWS': 'RAINEWS',
    'SCUOLA': 'SCUOLA',
    'STORIA': 'STORIA',
    'ZEETV': 'ZEETV',
    'ZEECIN': 'ZEECIN',
    'SETAS': 'SETAS',
    'MAX': 'MAX',
    'VENUS': 'VENUS',
    'SEXTRM': 'SEXTRM',
    'PENTHG': 'PENTHG',
    'HOTTAB': 'HOTTAB',
    'HOTMAN': 'HOTMAN',
    'VIVID': 'VIVID',
    'DORCEL': 'DORCEL',
    'VIXEN': 'VIXEN',
    'HUSTLER': 'HUSTLER',
    'PBTVHD': 'PBTVHD',
    'HOTHD': 'HOTHD',
    'FTV4K': 'FTV4K',
})


# Mantém o comportamento TLS do script original; recomenda-se validar certificados em produção.
ssl._create_default_https_context = ssl._create_unverified_context


def lisboa():
    if ZoneInfo:
        try:
            return ZoneInfo('Europe/Lisbon')
        except Exception:
            pass
    logging.warning('Timezone Europe/Lisbon indisponível; instalar tzdata para Windows: pip install tzdata')
    return timezone.utc


def http_json(url):
    req = urllib.request.Request(url, headers={
        'Origin': 'https://www.meo.pt', 'Referer': 'https://www.meo.pt/',
        'User-Agent': ('Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36'),
        'Accept': '*/*',
    })
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logging.warning('HTTP %s em %s', resp.status, url)
                return None
            return json.loads(resp.read().decode('utf-8'))
    except Exception as exc:
        logging.error('Pedido HTTP falhou: %s (%s)', exc, url)
        return None


def canais_meo():
    data = http_json('https://meogouser.apps.meo.pt/Services/GridTv/GridTv.svc/GetContentsForChannels?userAgent=IPTV_OFR_GTV')
    if not data or data.get('Status') != 'OK':
        return []
    canais = []
    vistos_call = set()
    vistos_tvg = set()
    for ch in data.get('Result', []):
        call = ch.get('CallLetter')
        if call not in MEO_TO_TVG or call in vistos_call:
            continue
        tvg_id = MEO_TO_TVG[call]
        if tvg_id in vistos_tvg:
            logging.warning('ID XMLTV duplicado %s (canal %s); ignorado', tvg_id, call)
            continue
        nome = ch.get('Name') or ch.get('Title') or ch.get('ChannelName') or ch.get('Description') or call
        icon = next((ch.get(k) for k in ('LogoUrl', 'LinkToLogo', 'Logo', 'Image', 'ImageUrl') if isinstance(ch.get(k), str) and ch.get(k)), None)
        canais.append((call, nome, icon))
        vistos_call.add(call)
        vistos_tvg.add(tvg_id)
    ausentes = sorted(set(MEO_TO_TVG) - vistos_call)
    if ausentes:
        logging.info('IDs configurados não devolvidos pela API MEO (%d): %s', len(ausentes), ', '.join(ausentes))
    return canais


def programas_meo(call, data):
    url = ('https://meogouser.apps.meo.pt/Services/GridTv/GridTv.svc/'
           'GetLiveChannelProgramsByDate?callLetter=' + urllib.parse.quote(call) +
           '&date=' + data + '&userAgent=IPTV_OFR_GTV')
    resp = http_json(url)
    return resp.get('Result', []) or [] if resp and resp.get('Status') == 'OK' else []


def data_xmltv(valor, tz):
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(valor, fmt).replace(tzinfo=timezone.utc).astimezone(tz).strftime('%Y%m%d%H%M%S %z')
        except ValueError:
            pass
    raise ValueError('Data desconhecida: ' + repr(valor))


def imagem_programa(call, titulo):
    return ('https://cdn-er-images.online.meo.pt/eemstb/ImageHandler.ashx'
            '?chCallLetter=' + urllib.parse.quote(call) + '&progTitle=' + urllib.parse.quote(titulo) +
            '&profile=16_9&profileFallback=false&noFallback=true'
            '&appSource=PC_CHROME_PWA&width=1920&csf')


def temporada_episodio(titulo, prog):
    m = re.match(r'.*(\s+|:)T(\d+)(?:\s+-?\s*Ep\.\s*)?(\d+)?$', titulo)
    if m:
        season = max(int(m.group(2))-1, 0)
        episode = max(int(m.group(3))-1, 0) if m.group(3) else 0
        ET.SubElement(prog, 'episode-num', {'system': 'xmltv_ns'}).text = f'{season}.{episode}.0/1'
    else:
        m = re.match(r'.*\s+Ep\.\s*(\d+)$', titulo)
        if m:
            ET.SubElement(prog, 'episode-num', {'system': 'xmltv_ns'}).text = f'0.{max(int(m.group(1))-1, 0)}.0/1'


def extrair(tz):
    canais = canais_meo()
    if not canais:
        raise RuntimeError('Nenhum canal obtido; ficheiros anteriores não serão alterados')
    logging.info('Canais selecionados: %d', len(canais))
    raiz = ET.Element('tv', {'generator-info-name': 'meo-epg'})
    for call, nome, icon in canais:
        ch = ET.SubElement(raiz, 'channel', {'id': MEO_TO_TVG[call]})
        ET.SubElement(ch, 'display-name', {'lang': 'pt'}).text = nome
        if icon:
            ET.SubElement(ch, 'icon', {'src': icon})
        ET.SubElement(ch, 'url').text = BASE_URL
    hoje = datetime.now(tz)
    dias = [(hoje + timedelta(days=d)).strftime('%Y-%m-%d') for d in range(-NR_DAYS_PAST, NR_DAYS_FUTURE+1)]
    logging.info('Janela: %s -> %s', dias[0], dias[-1])
    vistos = set()
    for i, (call, nome, _) in enumerate(canais, 1):
        cid = MEO_TO_TVG[call]
        logging.info('[%d/%d] %s (%s)', i, len(canais), nome, call)
        for dia in dias:
            for item in programas_meo(call, dia):
                try:
                    inicio = data_xmltv(item['StartDate'], tz)
                    fim = data_xmltv(item['EndDate'], tz)
                except (KeyError, ValueError, TypeError):
                    continue
                key = (cid, inicio)
                if key in vistos:
                    continue
                vistos.add(key)
                titulo = item.get('Title') or 'Sem titulo'
                p = ET.SubElement(raiz, 'programme', {'start': inicio, 'stop': fim, 'channel': cid})
                ET.SubElement(p, 'title', {'lang': 'pt'}).text = titulo
                desc = item.get('Synopsis') or item.get('Description') or ''
                if desc:
                    ET.SubElement(p, 'desc', {'lang': 'pt'}).text = desc
                ET.SubElement(p, 'icon', {'src': imagem_programa(call, titulo)})
                temporada_episodio(titulo, p)
            time.sleep(0.1)
    if not vistos:
        raise RuntimeError('Extração sem programas; ficheiros anteriores não serão alterados')
    logging.info('Extraídos %d programas', len(vistos))
    return raiz


def chave(p):
    # Canal e início identificam o mesmo evento, mesmo que o título/descrição mudem.
    return (p.get('channel'), p.get('start'))


def carregar_acumulado(path):
    with gzip.open(path, 'rb') as f:
        root = ET.parse(f).getroot()
    if root.tag != 'tv':
        raise ValueError('O GZ existente não contém um XMLTV válido')
    return root


def combinar(antigo, novo):
    # Preferir metadados recentes quando o canal já existe.
    canais = {c.get('id'): c for c in antigo.findall('channel')}
    for c in novo.findall('channel'):
        cid = c.get('id')
        if cid in canais:
            antigo.remove(canais[cid])
        antigo.append(c)
        canais[cid] = c
    programas = {chave(p): p for p in antigo.findall('programme')}
    adicionados = 0
    atualizados = 0
    for p in novo.findall('programme'):
        k = chave(p)
        if k in programas:
            antigo.remove(programas[k])
            atualizados += 1
        else:
            adicionados += 1
        antigo.append(p)
        programas[k] = p
    # Ordenação por canal e data, útil para leitores XMLTV.
    canais_ordenados = sorted(antigo.findall('channel'), key=lambda e: e.get('id') or '')
    programas_ordenados = sorted(antigo.findall('programme'), key=lambda e: (e.get('channel') or '', e.get('start') or ''))
    antigo[:] = canais_ordenados + programas_ordenados
    return antigo, adicionados, atualizados


def escrever_xml_atomico(root, destino):
    destino = Path(destino)
    fd, temp = tempfile.mkstemp(prefix='.epg_xml_', suffix='.tmp', dir=destino.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            ET.ElementTree(root).write(f, encoding='utf-8', xml_declaration=True)
        os.replace(temp, destino)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def escrever_gz_atomico(root, destino):
    destino = Path(destino)
    fd, temp = tempfile.mkstemp(prefix='.epg_gz_', suffix='.tmp', dir=destino.parent)
    try:
        with os.fdopen(fd, 'wb') as raw:
            with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=9) as gz:
                ET.ElementTree(root).write(gz, encoding='utf-8', xml_declaration=True)
        # Confirmar que o ficheiro novo é legível antes de substituir o antigo.
        carregar_acumulado(temp)
        os.replace(temp, destino)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def juntar_xmls_da_pasta(pasta_xml):
    """Reconstrói o XMLTV usando EXCLUSIVAMENTE os XML individuais da pasta."""
    ficheiros = sorted(pasta_xml.glob('*.xml'), key=lambda p: (datetime.strptime(p.stem[len('epg_meogo_'):], '%d-%m-%Y') if re.fullmatch(r'epg_meogo_\d{2}-\d{2}-\d{4}', p.stem) else datetime.min, p.name))
    if not ficheiros:
        raise RuntimeError('Não existem ficheiros .xml em output_epg')

    raiz = ET.Element('tv', {'generator-info-name': 'meo-epg'})
    canais = {}
    programas = {}
    for ficheiro in ficheiros:
        logging.info('A juntar: %s', ficheiro.name)
        try:
            xml = ET.parse(ficheiro).getroot()
        except (ET.ParseError, OSError) as e:
            raise RuntimeError(f'XML inválido em {ficheiro.name}: {e}. GZ anterior mantido.') from e
        if xml.tag != 'tv':
            raise RuntimeError(f'{ficheiro.name} não é XMLTV. GZ anterior mantido.')
        for canal in xml.findall('channel'):
            cid = canal.get('id')
            if cid:
                canais[cid] = canal
        logging.info('  Canais: %d | Programas: %d', len(xml.findall('channel')), len(xml.findall('programme')))
        for programa in xml.findall('programme'):
            k = chave(programa)
            if all(k):
                # Se o mesmo evento existir em várias extrações, prevalece o último XML.
                programas[k] = programa

    if not programas:
        raise RuntimeError('Os XML não contêm programas. GZ anterior mantido.')
    for cid in sorted(canais):
        raiz.append(canais[cid])
    for k in sorted(programas):
        raiz.append(programas[k])
    return raiz, len(ficheiros), len(programas)


def escolher_acao():
    print("\n" + "=" * 62)
    print("                 MEO EPG - MENU PRINCIPAL")
    print("=" * 62)
    print("  [1] Unir XML da pasta num XML.GZ para OTT (SEM extrair)")
    print("  [2] Fazer nova extracao MEO e atualizar o XML.GZ")
    print("  [0] Sair")
    print("=" * 62)
    while True:
        try:
            escolha = input("Escolhe uma opcao [1/2/0]: ").strip()
        except EOFError:
            raise RuntimeError("Sem entrada interativa. Para automatizar, usa --unir ou --extrair")
        if escolha in ("0", "1", "2"):
            return escolha
        print("Opcao invalida. Escolhe 1, 2 ou 0.")


def main():
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
    pasta = Path(__file__).resolve().parent
    pasta_xml = pasta / 'output_epg'
    pasta_gz = pasta / 'EPG_UPDATE'
    pasta_xml.mkdir(parents=True, exist_ok=True)
    pasta_gz.mkdir(parents=True, exist_ok=True)

    argumentos = sys.argv[1:]
    if not argumentos:
        escolha = escolher_acao()
    elif argumentos == ['--unir']:
        escolha = '1'
    elif argumentos == ['--extrair']:
        escolha = '2'
    else:
        print('Uso: python epg_meogo_menu.py [--unir | --extrair]')
        sys.exit(2)
    if escolha == '0':
        print('Operacao cancelada.')
        return

    if escolha == '2':
        tz = lisboa()
        nome_data = datetime.now(tz).strftime('%d-%m-%Y')
        xml_datado = pasta_xml / f'epg_meogo_{nome_data}.xml'
        logging.info('A iniciar nova extracao MEO...')
        novo = extrair(tz)
        if not novo.findall('programme'):
            raise RuntimeError('Extracao vazia. Nao se alterou o historico.')
        escrever_xml_atomico(novo, xml_datado)
        logging.info('XML novo guardado: %s (%d programas)', xml_datado, len(novo.findall('programme')))
    else:
        logging.info('Modo UNIR: nao sera feita qualquer pesquisa na MEO.')

    # Os XML datados em output_epg nunca sao alterados pela uniao.
    # O XMLTV combinado e escrito atomicamente para evitar perder o anterior.
    raiz, quantidade_xml, quantidade_programas = juntar_xmls_da_pasta(pasta_xml)
    destino = pasta_gz / OUTPUT_GZ
    escrever_gz_atomico(raiz, destino)
    print('\n' + '=' * 62)
    print('                XMLTV PARA OTT CRIADO')
    print('=' * 62)
    print(f'  XML originais lidos: {quantidade_xml}')
    for ficheiro in sorted(pasta_xml.glob('*.xml')):
        print(f'   - {ficheiro.name}')
    print(f'  Programas unicos no resultado: {quantidade_programas}')
    print(f'  Canais: {len(raiz.findall("channel"))}')
    print(f'  Ficheiro: {destino}')
    print(f'  Tamanho: {destino.stat().st_size:,} bytes')
    print('=' * 62)
    print('Os XML originais nao foram alterados.')


if __name__ == '__main__':
    try:
        main()
    except Exception as erro:
        logging.error('Operacao falhou: %s', erro)
        raise SystemExit(1)
