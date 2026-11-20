import requests

print("Por favor aguarde, a criar lista de IDs...")
# Função para buscar e processar os dados de uma página específica
def process_page(url):
    response = requests.get(url)
    data = response.json()
    lines = []
    for item in data['value']:
        title = item.get('Title', '')
        friendly_url_name = item.get('FriendlyUrlName', '')
        line = f"Title: \"{title}\" --- FriendlyUrlName: \"{friendly_url_name}\""
        lines.append(line)
    return lines

# Função principal para percorrer todas as páginas e salvar os resultados em um arquivo
def main():
    base_url = "http://ott.online.meo.pt/catalog/v9/Channels?$format=json&UserAgent=TVOS&$skip="
    start_page = 0
    end_page = 1000
    result_file = "Lista_canais_ID-TVOS.txt"

    with open(result_file, 'w', encoding='utf-8') as file:
        for page_number in range(start_page, end_page + 1):
            url = f"{base_url}{page_number * 10}"  # Assuming 10 items per page
            lines = process_page(url)
            for line in lines:
                file.write(line + '\n')
            print(f"Processed page {page_number} out of {end_page}")

    print("All pages processed. Results saved in", result_file)

if __name__ == "__main__":
    main()
