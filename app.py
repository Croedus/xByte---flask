from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify  # Import potřebných modulů z Flasku
import mysql.connector  # Modul pro připojení k MySQL databázi
from werkzeug.security import generate_password_hash, check_password_hash  # Nástroje pro bezpečnou práci s hesly
from flask_mail import Mail, Message  # Funkce pro odesílání e-mailů
from functools import wraps
import json  # Modul pro práci s JSON daty

# Inicializace Flask aplikace
app = Flask(__name__)  # Vytvoření instance Flask aplikace
app.secret_key = 'your_secret_key'  # Tajný klíč pro šifrování session dat (v produkci by měl být silnější a uložený bezpečněji)


# Dekorátor pro kontrolu, zda má uživatel administrátorská oprávnění
def admin_required(f):
    """
    Dekorátor, který zajišťuje, že k danému route má přístup pouze administrátor.
    Pokud uživatel není přihlášen nebo nemá roli admin, je přesměrován.
    
    Použití:
    @app.route('/admin/...')
    @admin_required
    def admin_route():
        # kód funkce
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Kontrola, zda je uživatel přihlášen
        if 'user_id' not in session:
            flash("Pro přístup do administrace se musíte přihlásit.", "error")
            return redirect(url_for('login'))
        
        # Kontrola role uživatele
        conn = get_db_connection()
        if not conn:
            flash("Chyba připojení k databázi.", "error")
            return redirect(url_for('index'))
            
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT role FROM xbyte WHERE id = %s", (session['user_id'],))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user or user['role'] != 'admin':
            flash("Nemáte oprávnění pro přístup do administrace.", "error")
            return redirect(url_for('index'))
            
        return f(*args, **kwargs)
    return decorated_function

# Konfigurace pro odesílání e-mailů
app.config['MAIL_SERVER'] = 'smtp.seznam.cz'  # SMTP server pro odesílání e-mailů
app.config['MAIL_PORT'] = 465  # Port SMTP serveru
app.config['MAIL_USE_TLS'] = False  # Nepoužívat TLS šifrování
app.config['MAIL_USE_SSL'] = True  # Používat SSL šifrování
app.config['MAIL_USERNAME'] = 'xbyteprojekt@seznam.cz'  # E-mailová adresa pro odesílání
app.config['MAIL_PASSWORD'] = 'test1234'  # Heslo k e-mailové adrese (v produkci by mělo být uloženo bezpečněji)
mail = Mail(app)  # Inicializace mail modulu s konfigurací aplikace

# Databázové tabulky - definice pro vytvoření (SQL příkazy pro vytvoření tabulek)
DB_TABLES = {
    # Tabulka uživatelů s údaji o registrovaných uživatelích
    'xbyte': """
        CREATE TABLE xbyte (
            id INT AUTO_INCREMENT PRIMARY KEY,  # Unikátní identifikátor uživatele
            username VARCHAR(100) NOT NULL UNIQUE,  # Uživatelské jméno (musí být unikátní)
            email VARCHAR(100) NOT NULL UNIQUE,  # E-mail (musí být unikátní)
            password VARCHAR(255) NOT NULL,  # Hashované heslo
            firstname VARCHAR(100),  # Jméno
            lastname VARCHAR(100),  # Příjmení
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  # Datum registrace (automaticky vyplněno)
            role VARCHAR(20) DEFAULT 'user'  # Role uživatele (admin/user) - přidaná pro administraci
        )
    """,
    # Tabulka produktů s informacemi o nabízených produktech
    'xbyte_produkty': """
        CREATE TABLE xbyte_produkty (
            id INT AUTO_INCREMENT PRIMARY KEY,  # Unikátní identifikátor produktu
            name VARCHAR(100) NOT NULL,  # Název produktu
            description TEXT,  # Popis produktu
            price DECIMAL(10,2) NOT NULL,  # Cena produktu (desetinné číslo s přesností na 2 desetinná místa)
            stock INT,  # Počet kusů na skladě
            image VARCHAR(255)  # Cesta k obrázku produktu
        )
    """,
    # Tabulka objednávek s informacemi o vytvořených objednávkách
    'xbyte_objednavky': """
        CREATE TABLE xbyte_objednavky (
            id INT AUTO_INCREMENT PRIMARY KEY,  # Unikátní identifikátor objednávky
            user_id INT NOT NULL,  # Odkaz na uživatele, který objednávku vytvořil
            celkova_cena DECIMAL(10,2) NOT NULL,  # Celková cena objednávky
            datum_objednavky TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  # Datum vytvoření objednávky
            telefon VARCHAR(20),  # Telefonní číslo zákazníka
            ulice VARCHAR(100),  # Ulice pro doručení
            cislo_popisne VARCHAR(20),  # Číslo popisné
            mesto VARCHAR(100),  # Město
            psc VARCHAR(10),  # PSČ
            zeme VARCHAR(100),  # Země
            shipping_option VARCHAR(50),  # Způsob dopravy
            payment_option VARCHAR(50),  # Způsob platby
            FOREIGN KEY (user_id) REFERENCES xbyte(id)  # Cizí klíč odkazující na tabulku uživatelů
        )
    """,
    # Tabulka položek objednávky s informacemi o jednotlivých produktech v objednávce
    'xbyte_polozky_objednavky': """
        CREATE TABLE xbyte_polozky_objednavky (
            id INT AUTO_INCREMENT PRIMARY KEY,  # Unikátní identifikátor položky objednávky
            objednavka_id INT NOT NULL,  # Odkaz na objednávku, ke které položka patří
            produkt_id INT NOT NULL,  # Odkaz na produkt
            mnozstvi INT NOT NULL,  # Počet kusů produktu
            cena_za_kus DECIMAL(10,2) NOT NULL,  # Cena za jeden kus (pro případ změny ceny produktu v budoucnu)
            FOREIGN KEY (objednavka_id) REFERENCES xbyte_objednavky(id),  # Cizí klíč odkazující na tabulku objednávek
            FOREIGN KEY (produkt_id) REFERENCES xbyte_produkty(id)  # Cizí klíč odkazující na tabulku produktů
        )
    """
}


def get_db_connection():
    """
    Vytvoří a vrátí připojení k databázi. 
    Pokud databázové tabulky neexistují, vytvoří je.
    
    Returns:
        mysql.connector.connection: Připojení k databázi, nebo None v případě chyby
    """
    try:
        # Vytvoření připojení k databázi
        conn = mysql.connector.connect(
            host='dbs.spskladno.cz',  # Adresa databázového serveru
            user='student20',  # Uživatelské jméno
            password='spsnet',  # Heslo
            database='vyuka20'  # Název databáze
        )
        
        # Kontrola existence tabulek a jejich případné vytvoření
        cursor = conn.cursor(buffered=True)  # Buffered cursor pro efektivní zpracování výsledků
        
        # Projdeme všechny definované tabulky a zkontrolujeme, zda existují
        for table_name, create_script in DB_TABLES.items():
            try:
                # Zkusíme provést dotaz na tabulku - pokud neexistuje, vyvolá to výjimku
                cursor.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
            except mysql.connector.errors.ProgrammingError:
                # Tabulka neexistuje, vytvoříme ji pomocí předem definovaného SQL
                cursor.execute(create_script)
                conn.commit()  # Potvrzení změn v databázi
        
        # Pro jistotu uzavřeme cursor (vytvoříme nový při specifických operacích)
        cursor.close()
        
        return conn  # Vracíme připojení k databázi
    except mysql.connector.Error as err:
        # Pokud dojde k chybě při připojení, vypíšeme ji a vrátíme None
        print(f"Chyba připojení k databázi: {err}")
        return None

def ensure_database_structure():
    """
    Zajišťuje správnou strukturu databáze - kontroluje existenci všech potřebných sloupců
    v tabulkách a případně je vytvoří/upraví.
    """
    try:
        # Získáme připojení k databázi
        conn = get_db_connection()
        if not conn:
            print("Nelze se připojit k databázi pro kontrolu struktury.")
            return
            
        # Použití buffered cursoru pro správu výsledků
        cursor = conn.cursor(buffered=True)
        
        # Kontrola struktury tabulky xbyte
        cursor.execute("SHOW COLUMNS FROM xbyte")
        existing_columns = [column[0] for column in cursor.fetchall()]
        
        # Sloupce, které by měly být v tabulce xbyte
        required_columns = {
            'role': 'VARCHAR(20) DEFAULT "user"',
            'firstname': 'VARCHAR(100)',
            'lastname': 'VARCHAR(100)',
            'registration_date': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        }
        
        # Přidání chybějících sloupců
        for column_name, column_definition in required_columns.items():
            if column_name not in existing_columns:
                try:
                    alter_query = f"ALTER TABLE xbyte ADD COLUMN {column_name} {column_definition}"
                    cursor.execute(alter_query)
                    conn.commit()
                    print(f"Sloupec '{column_name}' byl úspěšně přidán do tabulky xbyte")
                except mysql.connector.Error as err:
                    print(f"Chyba při přidávání sloupce '{column_name}': {err}")
        
        # Nastavení první registrované osoby jako administrátora
        cursor.execute("SELECT id FROM xbyte WHERE role = 'admin'")
        admin_exists = cursor.fetchone()
        
        if not admin_exists:
            # Najdi první registrovaný účet a nastav mu roli admin
            cursor.execute("SELECT id FROM xbyte ORDER BY registration_date ASC LIMIT 1")
            first_user = cursor.fetchone()
            
            if first_user:
                cursor.execute("UPDATE xbyte SET role = 'admin' WHERE id = %s", (first_user[0],))
                conn.commit()
                print(f"Uživatel s ID {first_user[0]} byl nastaven jako administrátor")
        
        # Kontrola dalších tabulek
        for table_name, create_script in DB_TABLES.items():
            try:
                # Zkusíme provést dotaz na tabulku - pokud neexistuje, vyvolá to výjimku
                cursor.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
            except mysql.connector.errors.ProgrammingError:
                # Tabulka neexistuje, vytvoříme ji pomocí předem definovaného SQL
                cursor.execute(create_script)
                conn.commit()
        
        # Explicitní uzavření kurzoru a připojení
        cursor.close()
        conn.close()
        print("Kontrola struktury databáze dokončena.")
        
    except mysql.connector.Error as e:
        # Zachycení specifických chyb MySQL
        print(f"MySQL chyba při kontrole struktury databáze: {e}")
    except Exception as e:
        # Zachycení jakýchkoli jiných neočekávaných chyb
        print(f"Chyba při kontrole struktury databáze: {e}")

# Zavolání funkce pro kontrolu a úpravu struktury databáze při startu aplikace
ensure_database_structure()

# ===== ZÁKLADNÍ ROUTY =====

@app.route('/')
def index():
    """
    Hlavní stránka webu - zobrazí úvodní stránku

    Returns:
        str: Vykreslená šablona index.html
    """
    return render_template('index.html')  # Vykreslení šablony index.html

@app.route('/produkty')
def produkty():
    """
    Stránka s produkty - načte všechny produkty z databáze a zobrazí je

    Returns:
        str: Vykreslená šablona produkty.html s daty o produktech
    """
    try:
        # Získání připojení k databázi
        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")  # Zobrazení chybové hlášky uživateli
            return render_template('produkty.html', produkty=[])  # Vykreslení šablony s prázdným seznamem produktů
            
        cursor = conn.cursor(dictionary=True)  # Cursor, který vrací výsledky jako slovníky
        cursor.execute("SELECT * FROM xbyte_produkty")  # SQL dotaz pro získání všech produktů
        produkty = cursor.fetchall()  # Načtení všech výsledků dotazu
        cursor.close()
        conn.close()
        return render_template('produkty.html', produkty=produkty)  # Vykreslení šablony s načtenými produkty
    except mysql.connector.Error as err:
        # Ošetření chyby při načítání produktů
        flash(f"Chyba při načítání produktů: {str(err)}", "error")
        return render_template('produkty.html', produkty=[])

@app.route('/kontakt')
def kontakt():
    """
    Stránka s kontaktními údaji

    Returns:
        str: Vykreslená šablona kontakt.html
    """
    return render_template('kontakt.html')

@app.route('/kosik')
def kosik():
    """
    Stránka s nákupním košíkem

    Returns:
        str: Vykreslená šablona kosik.html
    """
    return render_template('kosik.html')

@app.route('/kontaktuj', methods=['POST'])
def kontaktuj():
    """
    Zpracování kontaktního formuláře - odešle e-mail s obsahem formuláře

    Returns:
        werkzeug.wrappers.Response: Přesměrování zpět na stránku kontaktu
    """
    # Získání dat z formuláře
    jmeno = request.form.get('jmeno')
    email = request.form.get('email')
    zprava = request.form.get('zprava')
    
    try:
        # Vytvoření e-mailové zprávy
        msg = Message('Nová zpráva z kontaktního formuláře',
                    sender=app.config['MAIL_USERNAME'],  # Odesílatel je nastavený v konfiguraci
                    recipients=['xbyteprojekt@seznam.cz'])  # Příjemce zprávy
        msg.body = f"""
        Jméno: {jmeno}
        E-mail: {email}
        Zpráva:
        {zprava}
        """
        mail.send(msg)  # Odeslání e-mailu
        flash('Vaše zpráva byla úspěšně odeslána! Děkujeme za kontaktování.', 'success')  # Oznámení o úspěchu
    except Exception as e:
        # Ošetření chyby při odesílání
        flash(f'Při odesílání zprávy došlo k chybě: {str(e)}', 'error')
    
    return redirect(url_for('kontakt'))  # Přesměrování zpět na stránku kontaktu

# ===== AUTENTIZACE A UŽIVATELSKÝ ÚČET =====

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return render_template('login.html')
            
        cursor = conn.cursor(dictionary=True)

        try:
            # Hledání uživatele podle e-mailu
            cursor.execute("SELECT * FROM xbyte WHERE email = %s", (email,))
            user = cursor.fetchone()

            # Kontrola, zda uživatel existuje a heslo je správné
            if user and check_password_hash(user['password'], password):
                # Debug výpis
                print("Přihlašující se uživatel:", user)
                
                # Uložení údajů o přihlášeném uživateli do session
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['email'] = user['email']
                session['firstname'] = user['firstname']
                session['lastname'] = user['lastname']
                
                # Debug výpis role
                print("Role uživatele:", user.get('role', 'ROLE NENALEZENA'))
                
                # Explicitní nastavení role
                session['role'] = user.get('role', 'user')
                
                flash("Přihlášení úspěšné!", "success")
                return redirect(url_for('index'))  # Přesměrování na hlavní stránku
            else:
                flash("Neplatný email nebo heslo!", "error")
        except mysql.connector.Error as err:
            flash(f"Chyba při přihlášení: {err}", "error")
        finally:
            cursor.close()
            conn.close()

    # Pokud metoda není POST nebo při chybě v přihlášení, zobrazíme přihlašovací formulář
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Registrace nového uživatele - zpracovává registrační formulář a vytváří nového uživatele

    Returns:
        str nebo werkzeug.wrappers.Response: Vykreslená šablona nebo přesměrování po registraci
    """
    if request.method == 'POST':
        # Získání dat z registračního formuláře
        firstname = request.form['firstname']
        lastname = request.form['lastname']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        password_confirm = request.form['password_confirm']
        
        # Kontrola, zda se hesla shodují
        if password != password_confirm:
            flash("Hesla se neshodují!", "error")
            return render_template('register.html')
        
        # Hashování hesla pro bezpečné uložení
        hashed_password = generate_password_hash(password)

        # Připojení k databázi
        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return render_template('register.html')
            
        cursor = conn.cursor(dictionary=True)

        # Kontrola, zda uživatel již existuje
        cursor.execute("SELECT * FROM xbyte WHERE username = %s OR email = %s", (username, email))
        existing_user = cursor.fetchone()

        if existing_user:
            # Pokud uživatel existuje, zobrazíme chybovou hlášku
            if existing_user.get('username') == username:
                flash("Uživatelské jméno již existuje!", "error")
            else:
                flash("Email je již zaregistrován!", "error")
        else:
            # Vložení nového uživatele do tabulky xbyte
            sql_insert = """INSERT INTO xbyte 
                        (username, email, password, firstname, lastname) 
                        VALUES (%s, %s, %s, %s, %s)"""
            try:
                cursor.execute(sql_insert, (username, email, hashed_password, firstname, lastname))
                conn.commit()  # Potvrzení změn v databázi
                flash("Registrace úspěšná! Nyní se můžete přihlásit.", "success")
                cursor.close()
                conn.close()
                return redirect(url_for('login'))  # Přesměrování na přihlašovací stránku
            except mysql.connector.Error as err:
                flash(f"Chyba při registraci: {err}", "error")

        cursor.close()
        conn.close()

    # Pokud metoda není POST nebo při chybě v registraci, zobrazíme registrační formulář
    return render_template('register.html')

@app.route('/logout')
def logout():
    """
    Odhlášení uživatele - odstraní údaje o přihlášeném uživateli ze session

    Returns:
        werkzeug.wrappers.Response: Přesměrování na hlavní stránku
    """
    # Odstranění dat o přihlášení ze session
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('email', None)
    session.pop('firstname', None)
    session.pop('lastname', None)
    flash("Byli jste úspěšně odhlášeni.", "info")
    return redirect(url_for('index'))  # Přesměrování na hlavní stránku

@app.route('/nastaveni', methods=['GET', 'POST'])
def nastaveni():
    """
    Nastavení uživatelského účtu - umožňuje změnu hesla

    Returns:
        str nebo werkzeug.wrappers.Response: Vykreslená šablona nebo přesměrování
    """
    # Kontrola, zda je uživatel přihlášen
    if 'user_id' not in session:
        flash("Pro přístup k nastavení se musíte přihlásit!", "error")
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Získání dat z formuláře
        stare_heslo = request.form.get('stare_heslo')
        nove_heslo = request.form.get('nove_heslo')
        potvrzeni_hesla = request.form.get('potvrzeni_hesla')
        
        # Kontrola, že nové heslo a potvrzení se shodují
        if nove_heslo != potvrzeni_hesla:
            flash("Nové heslo a potvrzení hesla se neshodují!", "error")
            return redirect(url_for('nastaveni'))
        
        try:
            # Připojení k databázi
            conn = get_db_connection()
            if not conn:
                flash("Nelze se připojit k databázi!", "error")
                return redirect(url_for('nastaveni'))
                
            cursor = conn.cursor(dictionary=True)
            
            # Ověření starého hesla
            cursor.execute("SELECT password FROM xbyte WHERE id = %s", (session['user_id'],))
            user = cursor.fetchone()
            
            if not user or not check_password_hash(user['password'], stare_heslo):
                flash("Nesprávné stávající heslo!", "error")
                cursor.close()
                conn.close()
                return redirect(url_for('nastaveni'))
            
            # Aktualizace hesla
            hashed_password = generate_password_hash(nove_heslo)
            cursor.execute(
                "UPDATE xbyte SET password = %s WHERE id = %s",
                (hashed_password, session['user_id'])
            )
            conn.commit()  # Potvrzení změn v databázi
            
            flash("Heslo bylo úspěšně změněno.", "success")
            cursor.close()
            conn.close()
            
        except mysql.connector.Error as err:
            flash(f"Chyba při změně hesla: {str(err)}", "error")
    
    return render_template('nastaveni.html')

@app.route('/moje-objednavky')
def moje_objednavky():
    """
    Stránka s objednávkami přihlášeného uživatele - načte a zobrazí všechny objednávky uživatele

    Returns:
        str nebo werkzeug.wrappers.Response: Vykreslená šablona nebo přesměrování
    """
    # Kontrola, zda je uživatel přihlášen
    if 'user_id' not in session:
        flash("Pro zobrazení objednávek se musíte přihlásit!", "error")
        return redirect(url_for('login'))
    
    try:
        # Připojení k databázi
        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return render_template('moje_objednavky.html', objednavky=[])
            
        cursor = conn.cursor(dictionary=True)
        
        # Získání všech objednávek uživatele
        cursor.execute("""
            SELECT o.id, o.celkova_cena, o.datum_objednavky, 
                   COUNT(po.id) AS pocet_polozek,
                   o.telefon, o.ulice, o.cislo_popisne, o.mesto, o.psc, o.zeme,
                   o.shipping_option, o.payment_option
            FROM xbyte_objednavky o
            LEFT JOIN xbyte_polozky_objednavky po ON o.id = po.objednavka_id
            WHERE o.user_id = %s
            GROUP BY o.id
            ORDER BY o.datum_objednavky DESC
        """, (session['user_id'],))
        
        objednavky = cursor.fetchall()
        
        # Pro každou objednávku načteme detaily položek
        for obj in objednavky:
            cursor.execute("""
                SELECT po.id, po.mnozstvi, po.cena_za_kus, 
                       p.name, p.image
                FROM xbyte_polozky_objednavky po
                JOIN xbyte_produkty p ON po.produkt_id = p.id
                WHERE po.objednavka_id = %s
            """, (obj['id'],))
            
            obj['polozky'] = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('moje_objednavky.html', objednavky=objednavky)
    
    except mysql.connector.Error as err:
        flash(f"Chyba při načítání objednávek: {str(err)}", "error")
        return render_template('moje_objednavky.html', objednavky=[])

# ===== API ROUTY PRO KOŠÍK A OBJEDNÁVKY =====

@app.route('/check-auth')
def check_auth():
    """
    API pro kontrolu přihlášení uživatele
    
    Returns:
        flask.Response: JSON odpověď s informací o přihlášení
    """
    if 'user_id' in session:
        return jsonify({'authenticated': True})
    else:
        return jsonify({'authenticated': False})

@app.route('/get_user_data')
def get_user_data():
    """
    API pro získání údajů o přihlášeném uživateli
    
    Returns:
        flask.Response: JSON odpověď s údaji o přihlášeném uživateli
    """
    if 'user_id' in session:
        return jsonify({
            'authenticated': True,
            'firstname': session.get('firstname', ''),
            'lastname': session.get('lastname', ''),
            'email': session.get('email', '')
        })
    else:
        return jsonify({'authenticated': False})

@app.route('/get_stock_info', methods=['POST'])
def get_stock_info():
    """
    API pro získání informací o skladových zásobách produktů
    
    Returns:
        flask.Response: JSON odpověď s informacemi o skladových zásobách
    """
    try:
        # Získání dat z požadavku
        data = request.json
        product_ids = data.get('productIds', [])
        
        if not product_ids:
            return jsonify({})
        
        # Připojení k databázi
        conn = get_db_connection()
        if not conn:
            return jsonify({})
            
        cursor = conn.cursor(dictionary=True)
        
        # Vytvoření výsledného slovníku s informacemi o skladových zásobách
        stock_info = {}
        
        # Načtení informací o skladových zásobách pro všechny produkty
        for product_id in product_ids:
            cursor.execute("SELECT stock FROM xbyte_produkty WHERE id = %s", (product_id,))
            result = cursor.fetchone()
            stock_info[product_id] = result['stock'] if result else 0
        
        cursor.close()
        conn.close()
        
        return jsonify(stock_info)
        
    except Exception as e:
        print(f"Chyba při získávání informací o skladových zásobách: {str(e)}")
        return jsonify({})

def send_order_emails(objednavka_id, produkty_html, adresa_html, shipping_info, payment_info, total_price):
    """
    Odešle potvrzovací e-maily o objednávce firmě a zákazníkovi
    
    Args:
        objednavka_id (int): ID objednávky
        produkty_html (str): HTML kód s přehledem produktů
        adresa_html (str): HTML kód s doručovací adresou
        shipping_info (str): Informace o způsobu dopravy
        payment_info (str): Informace o způsobu platby
        total_price (float): Celková cena objednávky
        
    Returns:
        bool: True pokud se e-maily odeslaly úspěšně, jinak False
    """
    try:
        # Odeslání e-mailu firmě
        msg_firma = Message(
            f'Nová objednávka #{objednavka_id}',
            sender=app.config['MAIL_USERNAME'],
            recipients=['xbyteprojekt@seznam.cz']
        )
        msg_firma.html = f"""
        <h2>Nová objednávka #{objednavka_id}</h2>
        <p><strong>Od zákazníka:</strong> {session.get('firstname', '')} {session.get('lastname', '')}</p>
        <p><strong>E-mail:</strong> {session.get('email', '')}</p>
        <p><strong>Uživatelské jméno:</strong> {session.get('username', '')}</p>
        
        {adresa_html}
        
        <p><strong>Způsob dopravy:</strong> {shipping_info}</p>
        <p><strong>Způsob platby:</strong> {payment_info}</p>
        
        <h3>Objednané položky:</h3>
        <p>{produkty_html}</p>
        
        <p><strong>Celková cena:</strong> {total_price} Kč</p>
        """
        mail.send(msg_firma)
        
        # Odeslání potvrzovacího e-mailu zákazníkovi
        msg_zakaznik = Message(
            f'Potvrzení objednávky #{objednavka_id}',
            sender=app.config['MAIL_USERNAME'],
            recipients=[session.get('email')]
        )
        msg_zakaznik.html = f"""
        <h2>Děkujeme za Vaši objednávku!</h2>
        <p>Vážený/á {session.get('firstname', '')} {session.get('lastname', '')},</p>
        <p>Vaše objednávka #{objednavka_id} byla úspěšně přijata.</p>
        
        {adresa_html}
        
        <p><strong>Způsob dopravy:</strong> {shipping_info}</p>
        <p><strong>Způsob platby:</strong> {payment_info}</p>
        
        <h3>Přehled objednaných položek:</h3>
        <p>{produkty_html}</p>
        
        <p><strong>Celková cena:</strong> {total_price} Kč</p>
        <p>O průběhu zpracování Vaší objednávky Vás budeme informovat.</p>
        <p>S pozdravem,<br>
        Tým xByte</p>
        """
        mail.send(msg_zakaznik)
        return True
    except Exception as e:
        print(f"Chyba při odesílání e-mailů: {str(e)}")
        return False

def send_cancel_order_emails(objednavka_id, produkty=None, total_price=0):
    """
    Odešle e-maily o zrušení objednávky firmě a zákazníkovi
    
    Args:
        objednavka_id (int): ID zrušené objednávky
        produkty (str, optional): HTML kód s přehledem produktů
        total_price (float, optional): Celková cena zrušené objednávky
        
    Returns:
        bool: True pokud se e-maily odeslaly úspěšně, jinak False
    """
    try:
        # Odeslání e-mailu firmě
        msg_firma = Message(
            f'Zrušení objednávky #{objednavka_id}',
            sender=app.config['MAIL_USERNAME'],
            recipients=['xbyteprojekt@seznam.cz']
        )
        msg_firma.html = f"""
        <h2>Zrušení objednávky #{objednavka_id}</h2>
        <p><strong>Zákazník:</strong> {session.get('firstname', '')} {session.get('lastname', '')}</p>
        <p><strong>E-mail:</strong> {session.get('email', '')}</p>
        <p><strong>Uživatelské jméno:</strong> {session.get('username', '')}</p>
        
        <p>Zákazník zrušil objednávku #{objednavka_id}. Veškeré položky byly vráceny na sklad.</p>
        
        {f"<h3>Zrušené položky:</h3><p>{produkty}</p>" if produkty else ""}
        {f"<p><strong>Celková cena:</strong> {total_price} Kč</p>" if total_price else ""}
        """
        mail.send(msg_firma)
        
        # Odeslání potvrzovacího e-mailu zákazníkovi
        msg_zakaznik = Message(
            f'Potvrzení zrušení objednávky #{objednavka_id}',
            sender=app.config['MAIL_USERNAME'],
            recipients=[session.get('email')]
        )
        msg_zakaznik.html = f"""
        <h2>Potvrzení zrušení objednávky</h2>
        <p>Vážený/á {session.get('firstname', '')} {session.get('lastname', '')},</p>
        <p>Vaše objednávka #{objednavka_id} byla úspěšně zrušena.</p>
        
        {f"<h3>Zrušené položky:</h3><p>{produkty}</p>" if produkty else ""}
        {f"<p><strong>Celková cena:</strong> {total_price} Kč</p>" if total_price else ""}
        
        <p>Všechny položky byly vráceny zpět na sklad.</p>
        <p>Pokud jste již provedli platbu, bude vám vrácena v nejbližší možné době.</p>
        <p>V případě jakýchkoliv dotazů nás neváhejte kontaktovat.</p>
        <p>S pozdravem,<br>
        Tým xByte</p>
        """
        mail.send(msg_zakaznik)
        return True
    except Exception as e:
        print(f"Chyba při odesílání e-mailů o zrušení objednávky: {str(e)}")
        return False

@app.route('/place_order', methods=['POST'])
def place_order():
    """
    API pro vytvoření objednávky - zpracuje data z košíku a vytvoří objednávku v databázi
    
    Returns:
        flask.Response: JSON odpověď s výsledkem vytvoření objednávky
    """
    # Kontrola, zda je uživatel přihlášen
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Pro dokončení objednávky se musíte přihlásit'
        })
    
    try:
        # Získání dat z požadavku
        data = request.json
        cart_items = data.get('items', [])  # Položky v košíku
        total_price = data.get('totalPrice', 0)  # Celková cena
        shipping_option = data.get('shippingOption', '')  # Způsob dopravy
        payment_option = data.get('paymentOption', '')  # Způsob platby
        billing_data = data.get('billingData', {})  # Fakturační údaje
        
        # Kontrola povinných fakturačních údajů
        required_fields = ['phone', 'street', 'house_number', 'city', 'zip', 'country']
        for field in required_fields:
            if not billing_data.get(field):
                return jsonify({
                    'success': False,
                    'message': f'Chybí povinný údaj: {field}'
                })
        
        if not cart_items:
            return jsonify({
                'success': False,
                'message': 'Košík je prázdný'
            })
        
        # Připojení k databázi
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Chyba připojení k databázi'
            })
        
        cursor = conn.cursor(dictionary=True)
        
        # Kontrola dostupnosti zboží
        insufficient_stock = []
        for item in cart_items:
            cursor.execute("SELECT stock FROM xbyte_produkty WHERE id = %s", (item['id'],))
            product = cursor.fetchone()
            if not product or product['stock'] < item['quantity']:
                # Zjistíme jméno produktu pro lepší chybovou hlášku
                cursor.execute("SELECT name, stock FROM xbyte_produkty WHERE id = %s", (item['id'],))
                product_info = cursor.fetchone()
                insufficient_stock.append({
                    'id': item['id'],
                    'name': product_info['name'] if product_info else f"Produkt ID: {item['id']}",
                    'requested': item['quantity'],
                    'available': product_info['stock'] if product_info else 0
                })
        
        if insufficient_stock:
            # Sestavení chybové zprávy
            return jsonify({
                'success': False,
                'message': 'Nedostatek zboží na skladě',
                'insufficientStock': insufficient_stock
            })
        
        # Vytvoření záznamu objednávky s fakturačními údaji
        cursor.execute(
            """INSERT INTO xbyte_objednavky 
               (user_id, celkova_cena, telefon, ulice, cislo_popisne, mesto, psc, zeme, shipping_option, payment_option) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                session['user_id'], 
                total_price, 
                billing_data.get('phone', ''),
                billing_data.get('street', ''),
                billing_data.get('house_number', ''),
                billing_data.get('city', ''),
                billing_data.get('zip', ''),
                billing_data.get('country', ''),
                shipping_option,
                payment_option
            )
        )
        conn.commit()
        objednavka_id = cursor.lastrowid  # Získání ID nově vytvořené objednávky
        
        # Vložení položek objednávky a aktualizace skladu
        for item in cart_items:
            # Vložení položky objednávky
            cursor.execute(
                "INSERT INTO xbyte_polozky_objednavky (objednavka_id, produkt_id, mnozstvi, cena_za_kus) VALUES (%s, %s, %s, %s)",
                (objednavka_id, item['id'], item['quantity'], item['price'])
            )
            
            # Aktualizace počtu kusů na skladě
            cursor.execute(
                "UPDATE xbyte_produkty SET stock = stock - %s WHERE id = %s",
                (item['quantity'], item['id'])
            )
        
        conn.commit()
        
        # Získání informací o produktech pro e-mail
        produkty_html = ""
        for item in cart_items:
            cursor.execute("SELECT name FROM xbyte_produkty WHERE id = %s", (item['id'],))
            produkt = cursor.fetchone()
            if produkt:
                produkty_html += f"{produkt['name']} - {item['quantity']} ks - {item['price']} Kč/ks - Celkem: {item['price'] * item['quantity']} Kč<br>"
        
        # Příprava adresy pro e-mail
        adresa_html = f"""
        <p><strong>Doručovací adresa:</strong><br>
        {billing_data.get('firstname', '')} {billing_data.get('lastname', '')}<br>
        {billing_data.get('street', '')} {billing_data.get('house_number', '')}<br>
        {billing_data.get('zip', '')} {billing_data.get('city', '')}<br>
        {billing_data.get('country', '')}<br>
        Tel: {billing_data.get('phone', '')}</p>
        """
        
        # Příprava informací o dopravě a platbě
        shipping_info = "Osobní odběr" if shipping_option == "pickup" else "Doručení na adresu"
        payment_info = "Hotově/kartou" if payment_option == "cash" else "Bankovním převodem"
        
        # Odeslání e-mailů s potvrzením
        send_order_emails(objednavka_id, produkty_html, adresa_html, shipping_info, payment_info, total_price)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Objednávka byla úspěšně vytvořena',
            'orderId': objednavka_id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Chyba při zpracování objednávky: {str(e)}'
        })

@app.route('/cancel_order', methods=['POST'])
def cancel_order():
    """
    API pro zrušení objednávky - zruší objednávku a vrátí produkty zpět na sklad
    
    Returns:
        flask.Response: JSON odpověď s výsledkem zrušení objednávky
    """
    # Kontrola, zda je uživatel přihlášen
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Pro zrušení objednávky se musíte přihlásit'
        })
    
    try:
        data = request.json
        order_id = data.get('orderId')  # ID objednávky ke zrušení
        
        if not order_id:
            return jsonify({
                'success': False,
                'message': 'Nebyl poskytnut identifikátor objednávky'
            })
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Chyba připojení k databázi'
            })
        
        cursor = conn.cursor(dictionary=True)
        
        # Nejprve ověříme, že objednávka patří aktuálnímu uživateli
        cursor.execute(
            "SELECT * FROM xbyte_objednavky WHERE id = %s AND user_id = %s",
            (order_id, session['user_id'])
        )
        order = cursor.fetchone()
        
        if not order:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': 'Objednávka nebyla nalezena nebo k ní nemáte přístup'
            })
        
        # Získání celkové ceny objednávky pro e-mail
        total_price = order['celkova_cena']
        
        # Nyní získáme položky objednávky pro následné vrácení zboží na sklad a pro e-mail
        cursor.execute(
            """
            SELECT po.produkt_id, po.mnozstvi, po.cena_za_kus, p.name 
            FROM xbyte_polozky_objednavky po
            JOIN xbyte_produkty p ON po.produkt_id = p.id
            WHERE po.objednavka_id = %s
            """,
            (order_id,)
        )
        order_items = cursor.fetchall()
        
        # Příprava informací o produktech pro e-mail
        produkty_html = ""
        for item in order_items:
            produkty_html += f"{item['name']} - {item['mnozstvi']} ks - {item['cena_za_kus']} Kč/ks - Celkem: {item['cena_za_kus'] * item['mnozstvi']} Kč<br>"
        
        # Vrácení produktů zpět na sklad
        for item in order_items:
            cursor.execute(
                "UPDATE xbyte_produkty SET stock = stock + %s WHERE id = %s",
                (item['mnozstvi'], item['produkt_id'])
            )
        
        # Odstranění položek objednávky
        cursor.execute(
            "DELETE FROM xbyte_polozky_objednavky WHERE objednavka_id = %s",
            (order_id,)
        )
        
        # Odstranění samotné objednávky
        cursor.execute(
            "DELETE FROM xbyte_objednavky WHERE id = %s",
            (order_id,)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Odeslání e-mailů o zrušení objednávky
        send_cancel_order_emails(order_id, produkty_html, total_price)
        
        return jsonify({
            'success': True,
            'message': 'Objednávka byla úspěšně zrušena'
        })
        
    except Exception as e:
        print(f"Chyba při rušení objednávky: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Chyba při zpracování požadavku: {str(e)}'
        })

# ===== ADMINISTRAČNÍ ROZHRANÍ =====

@app.route('/admin')
@admin_required
def admin_dashboard():
    """
    Hlavní stránka administrace.
    Zobrazuje přehled sekcí administračního rozhraní.
    """
    return render_template('admin/dashboard.html')

# ----- SPRÁVA PRODUKTŮ -----

@app.route('/admin/produkty')
@admin_required
def admin_produkty():
    """
    Správa produktů - zobrazuje seznam všech produktů s možností editace a smazání.
    """
    try:
        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return render_template('admin/produkty.html', produkty=[])
            
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM xbyte_produkty ORDER BY id DESC")
        produkty = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('admin/produkty.html', produkty=produkty)
    except mysql.connector.Error as err:
        flash(f"Chyba při načítání produktů: {str(err)}", "error")
        return render_template('admin/produkty.html', produkty=[])

@app.route('/admin/produkt/novy', methods=['GET', 'POST'])
@admin_required
def admin_novy_produkt():
    """
    Přidání nového produktu.
    GET: zobrazí formulář pro vytvoření produktu
    POST: zpracuje odeslaný formulář a vytvoří nový produkt
    """
    if request.method == 'POST':
        # Získání dat z formuláře
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        stock = request.form.get('stock', 0)
        image = request.form.get('image')
        
        # Validace vstupů
        if not name or not price:
            flash("Název a cena jsou povinné položky.", "error")
            return render_template('admin/produkt_form.html')
            
        try:
            # Vložení do databáze
            conn = get_db_connection()
            if not conn:
                flash("Nelze se připojit k databázi!", "error")
                return render_template('admin/produkt_form.html')
                
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO xbyte_produkty (name, description, price, stock, image) VALUES (%s, %s, %s, %s, %s)",
                (name, description, price, stock, image)
            )
            conn.commit()
            cursor.close()
            conn.close()
            
            flash("Produkt byl úspěšně vytvořen.", "success")
            return redirect(url_for('admin_produkty'))
        except mysql.connector.Error as err:
            flash(f"Chyba při vytváření produktu: {str(err)}", "error")
            return render_template('admin/produkt_form.html')
        
    return render_template('admin/produkt_form.html')

@app.route('/admin/produkt/edit/<int:produkt_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_produkt(produkt_id):
    """
    Editace existujícího produktu.
    GET: zobrazí formulář s předvyplněnými daty produktu
    POST: zpracuje odeslaný formulář a aktualizuje produkt
    """
    conn = get_db_connection()
    if not conn:
        flash("Nelze se připojit k databázi!", "error")
        return redirect(url_for('admin_produkty'))
        
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        # Získání dat z formuláře
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        stock = request.form.get('stock', 0)
        image = request.form.get('image')
        
        # Validace vstupů
        if not name or not price:
            flash("Název a cena jsou povinné položky.", "error")
            cursor.execute("SELECT * FROM xbyte_produkty WHERE id = %s", (produkt_id,))
            produkt = cursor.fetchone()
            return render_template('admin/produkt_form.html', produkt=produkt)
        
        try:    
            # Aktualizace v databázi
            cursor.execute(
                "UPDATE xbyte_produkty SET name = %s, description = %s, price = %s, stock = %s, image = %s WHERE id = %s",
                (name, description, price, stock, image, produkt_id)
            )
            conn.commit()
            
            flash("Produkt byl úspěšně aktualizován.", "success")
            return redirect(url_for('admin_produkty'))
        except mysql.connector.Error as err:
            flash(f"Chyba při aktualizaci produktu: {str(err)}", "error")
            cursor.execute("SELECT * FROM xbyte_produkty WHERE id = %s", (produkt_id,))
            produkt = cursor.fetchone()
            return render_template('admin/produkt_form.html', produkt=produkt)
    
    # Načtení produktu pro editaci
    cursor.execute("SELECT * FROM xbyte_produkty WHERE id = %s", (produkt_id,))
    produkt = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not produkt:
        flash("Produkt nebyl nalezen.", "error")
        return redirect(url_for('admin_produkty'))
        
    return render_template('admin/produkt_form.html', produkt=produkt)

@app.route('/admin/produkt/delete/<int:produkt_id>', methods=['POST'])
@admin_required
def admin_delete_produkt(produkt_id):
    """
    Smazání produktu.
    Kontroluje, zda produkt není součástí existujících objednávek, a pokud ne, smaže ho.
    """
    conn = get_db_connection()
    if not conn:
        flash("Nelze se připojit k databázi!", "error")
        return redirect(url_for('admin_produkty'))
        
    cursor = conn.cursor()
    
    try:
        # Kontrola, zda produkt není v objednávkách
        cursor.execute("SELECT COUNT(*) as count FROM xbyte_polozky_objednavky WHERE produkt_id = %s", (produkt_id,))
        result = cursor.fetchone()
        
        if result[0] > 0:
            flash("Produkt nelze smazat, protože je součástí existujících objednávek.", "error")
        else:
            cursor.execute("DELETE FROM xbyte_produkty WHERE id = %s", (produkt_id,))
            conn.commit()
            flash("Produkt byl úspěšně smazán.", "success")
    except mysql.connector.Error as err:
        flash(f"Chyba při mazání produktu: {str(err)}", "error")
    
    cursor.close()
    conn.close()
    return redirect(url_for('admin_produkty'))

# ----- SPRÁVA OBJEDNÁVEK -----

@app.route('/admin/objednavky')
@admin_required
def admin_objednavky():
    """
    Správa objednávek - zobrazuje seznam všech objednávek s možností zobrazení detailů.
    """
    try:
        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return render_template('admin/objednavky.html', objednavky=[])
            
        cursor = conn.cursor(dictionary=True)
        
        # Získání všech objednávek s informacemi o uživatelích
        cursor.execute("""
            SELECT o.*, u.username, u.email 
            FROM xbyte_objednavky o
            JOIN xbyte u ON o.user_id = u.id
            ORDER BY o.datum_objednavky DESC
        """)
        objednavky = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return render_template('admin/objednavky.html', objednavky=objednavky)
    except mysql.connector.Error as err:
        flash(f"Chyba při načítání objednávek: {str(err)}", "error")
        return render_template('admin/objednavky.html', objednavky=[])

@app.route('/admin/objednavka/<int:objednavka_id>')
@admin_required
def admin_detail_objednavky(objednavka_id):
    """
    Zobrazení detailu objednávky včetně položek a informací o zákazníkovi.
    """
    try:
        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return redirect(url_for('admin_objednavky'))
            
        cursor = conn.cursor(dictionary=True)
        
        # Získání detailů objednávky
        cursor.execute("""
            SELECT o.*, u.username, u.email, u.firstname, u.lastname
            FROM xbyte_objednavky o
            JOIN xbyte u ON o.user_id = u.id
            WHERE o.id = %s
        """, (objednavka_id,))
        objednavka = cursor.fetchone()
        
        if not objednavka:
            cursor.close()
            conn.close()
            flash("Objednávka nebyla nalezena.", "error")
            return redirect(url_for('admin_objednavky'))
        
        # Získání položek objednávky
        cursor.execute("""
            SELECT po.*, p.name, p.image
            FROM xbyte_polozky_objednavky po
            JOIN xbyte_produkty p ON po.produkt_id = p.id
            WHERE po.objednavka_id = %s
        """, (objednavka_id,))
        polozky = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('admin/objednavka_detail.html', objednavka=objednavka, polozky=polozky)
    except mysql.connector.Error as err:
        flash(f"Chyba při načítání detailu objednávky: {str(err)}", "error")
        return redirect(url_for('admin_objednavky'))

# ----- SPRÁVA UŽIVATELŮ -----

@app.route('/admin/uzivatele')
@admin_required
def admin_uzivatele():
    """
    Správa uživatelů - zobrazuje seznam všech uživatelů s možností změny rolí.
    """
    try:
        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return render_template('admin/uzivatele.html', uzivatele=[])
            
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, email, firstname, lastname, registration_date, role FROM xbyte ORDER BY registration_date DESC")
        uzivatele = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('admin/uzivatele.html', uzivatele=uzivatele)
    except mysql.connector.Error as err:
        flash(f"Chyba při načítání uživatelů: {str(err)}", "error")
        return render_template('admin/uzivatele.html', uzivatele=[])

@app.route('/admin/uzivatel/<int:uzivatel_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_uzivatel(uzivatel_id):
    """
    Editace uživatele - umožňuje změnit roli uživatele (admin/user).
    """
    conn = get_db_connection()
    if not conn:
        flash("Nelze se připojit k databázi!", "error")
        return redirect(url_for('admin_uzivatele'))
        
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        # Zjistíme, co se má změnit
        role = request.form.get('role')
        if role in ['admin', 'user']:
            try:
                cursor.execute(
                    "UPDATE xbyte SET role = %s WHERE id = %s",
                    (role, uzivatel_id)
                )
                conn.commit()
                flash("Role uživatele byla změněna.", "success")
            except mysql.connector.Error as err:
                flash(f"Chyba při změně role uživatele: {str(err)}", "error")
        
        return redirect(url_for('admin_uzivatele'))
    
    # Načtení uživatele pro editaci
    cursor.execute("SELECT * FROM xbyte WHERE id = %s", (uzivatel_id,))
    uzivatel = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not uzivatel:
        flash("Uživatel nebyl nalezen.", "error")
        return redirect(url_for('admin_uzivatele'))
        
    return render_template('admin/uzivatel_form.html', uzivatel=uzivatel)

# ----- VYTVOŘENÍ PRVNÍHO ADMINISTRÁTORA -----
# Tento route můžete po prvním použití odstranit nebo zabezpečit

@app.route('/create-admin/<string:secret_key>')
def create_admin(secret_key):
    """
    Jednorázový route pro vytvoření prvního administrátora.
    Pro zabezpečení vyžaduje tajný klíč, který by měl být složitý.
    
    Použití:
    1. Přihlaste se jako uživatel, kterého chcete povýšit na administrátora
    2. Navštivte URL /create-admin/vas_tajny_klic
    3. Po úspěšném povýšení tento route odstraňte nebo zabezpečte
    """
    # !!! ZMĚŇTE TENTO KLÍČ !!! - použijte složitý řetězec
    if secret_key != 'tajny_klic_pro_vytvoreni_admina':
        flash("Neplatný klíč!", "error")
        return redirect(url_for('index'))
    
    # Musíte být přihlášeni
    if 'user_id' not in session:
        flash("Musíte být přihlášeni!", "error")
        return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return redirect(url_for('index'))
            
        cursor = conn.cursor()
        cursor.execute("UPDATE xbyte SET role = 'admin' WHERE id = %s", (session['user_id'],))
        conn.commit()
        cursor.close()
        conn.close()
        
        flash("Váš účet byl povýšen na administrátora!", "success")
        return redirect(url_for('index'))
    except mysql.connector.Error as err:
        flash(f"Chyba při povyšování uživatele: {str(err)}", "error")
        return redirect(url_for('index'))


# ===== SPUŠTĚNÍ APLIKACE =====

if __name__ == '__main__':
    # Spustí aplikaci na adrese 0.0.0.0 (což znamená, že je dostupná ze všech IP adres)
    # a na portu 5000. Parametr debug=True znamená, že aplikace běží v režimu ladění,
    # což umožňuje automatické restartování aplikace při změnách v kódu a zobrazuje chybové hlášky.
    app.run(host='0.0.0.0', port=5000, debug=True)