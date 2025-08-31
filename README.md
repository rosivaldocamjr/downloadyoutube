# DownloadYoutube (Flask)
Uma aplicação web simples e eficiente construída com Python e Flask para baixar vídeos do YouTube. A interface permite que os usuários colem uma URL, selecionem a qualidade desejada e baixem o conteúdo para visualização offline.

O projeto utiliza pytubefix para a lógica de download e FFmpeg para unir os streams de áudio e vídeo, garantindo arquivos MP4 de alta qualidade.

---

### ✨ Features
-Interface web limpa e intuitiva para facilitar o uso.

- Download de vídeos individuais do YouTube.

- Seleção de qualidade de vídeo (Melhor, 1080p, 720p, etc.).

- União automática de áudio e vídeo para downloads de alta qualidade que o YouTube serve separadamente.

- Nomes de arquivos sanitizados para evitar problemas no sistema de arquivos.

---

### 🛠️ Tecnologia Utilizada
- Backend: Python, Flask 

- Download Engine: Pytubefix 

- Processamento de Mídia: FFmpeg

- Frontend: HTML5 / CSS Básico

- Gerenciamento de Dependências: pip-tools (pip-compile, pip-sync)

---

### 📋 Pré-requisitos
Antes de começar, garanta que você tenha os seguintes softwares instalados em sua máquina:

- Python 3.10+

- Git

- FFmpeg: Essencial para o download em alta qualidade. Para verificar se está instalado, execute o comando abaixo no seu terminal. Você deve ver a versão do FFmpeg como resposta.

```Bash
ffmpeg -version
```

---

### 🚀 Instalação e Execução
Siga os passos abaixo para configurar e rodar o projeto localmente.

1. Clone o Repositório
Primeiro, clone este repositório para a sua máquina local.

```Bash
git clone <URL_DO_SEU_REPOSITORIO_GIT>
cd <NOME_DA_PASTA_DO_PROJETO>
```

2. Crie e Ative o Ambiente Virtual
É uma boa prática isolar as dependências do projeto em um ambiente virtual.

```Bash
# Crie o ambiente na pasta .venv
python -m venv .venv

# Ative o ambiente no Windows
.\.venv\Scripts\activate

# Ative o ambiente no macOS/Linux
source .venv/bin/activate
```

3. Instale as Dependências com pip-sync
Este projeto utiliza pip-tools para um gerenciamento preciso das dependências. Primeiro, instale a ferramenta e, em seguida, sincronize seu ambiente usando o arquivo 

requirements.in.

```Bash
# 1. Instale o pip-tools
pip install pip-tools

# 2. Sincronize o ambiente. O pip-sync instalará exatamente
#    o que está especificado no arquivo de requerimentos.
pip-sync requirements.in
```

4. Execute a Aplicação
Com tudo configurado, inicie o servidor Flask.

```Bash
flask run
```
O servidor estará disponível em http://127.0.0.1:5000.

--- 

💻 Como Usar
1. Abra seu navegador e acesse http://127.0.0.1:5000.

2. Cole a URL de um vídeo do YouTube no campo "URL do vídeo".

3. Selecione a qualidade desejada no menu dropdown.

4. Clique no botão "Baixar".

5. Aguarde o processamento. A página será recarregada e um link para o arquivo final aparecerá na seção de resultados.

6. Clique no link para baixar o vídeo para o seu computador.
