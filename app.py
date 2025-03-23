from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import json

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Konfigurace pro odesílání e-mailů
app.config['MAIL_SERVER'] = 'smtp.seznam.cz'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'xbyteprojekt@seznam.cz'
app.config['MAIL_PASSWORD'] = 'test1234'
mail = Mail(app)

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host='dbs.spskladno.cz',
            user='student20',
            password='spsnet',
            database='vyuka20'
        )
        
        # Kontrola existence tabulky xbyte a případné vytvoření
        cursor = conn.cursor(buffered=True)
        try:
            cursor.execute("SELECT 1 FROM xbyte LIMIT 1")
        except mysql.connector.errors.ProgrammingError:
            # Tabulka neexistuje, vytvoříme ji
            cursor.execute("""
            CREATE TABLE xbyte (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                email VARCHAR(100) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                firstname VARCHAR(100),
                lastname VARCHAR(100),
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()
        
        # Kontrola existence tabulky xbyte_produkty a případné vytvoření
        try:
            cursor.execute("SELECT 1 FROM xbyte_produkty LIMIT 1")
        except mysql.connector.errors.ProgrammingError:
            # Tabulka neexistuje, vytvoříme ji
            cursor.execute("""
            CREATE TABLE xbyte_produkty (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                price DECIMAL(10,2) NOT NULL,
                stock INT,
                image VARCHAR(255)
            )
            """)
            conn.commit()
            
        # Kontrola existence tabulky xbyte_objednavky a případné vytvoření
        try:
            cursor.execute("SELECT 1 FROM xbyte_objednavky LIMIT 1")
        except mysql.connector.errors.ProgrammingError:
            # Tabulka neexistuje, vytvoříme ji
            cursor.execute("""
            CREATE TABLE xbyte_objednavky (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                celkova_cena DECIMAL(10,2) NOT NULL,
                datum_objednavky TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES xbyte(id)
            )
            """)
            conn.commit()
            
        # Kontrola existence tabulky xbyte_polozky_objednavky a případné vytvoření
        try:
            cursor.execute("SELECT 1 FROM xbyte_polozky_objednavky LIMIT 1")
        except mysql.connector.errors.ProgrammingError:
            # Tabulka neexistuje, vytvoříme ji
            cursor.execute("""
            CREATE TABLE xbyte_polozky_objednavky (
                id INT AUTO_INCREMENT PRIMARY KEY,
                objednavka_id INT NOT NULL,
                produkt_id INT NOT NULL,
                mnozstvi INT NOT NULL,
                cena_za_kus DECIMAL(10,2) NOT NULL,
                FOREIGN KEY (objednavka_id) REFERENCES xbyte_objednavky(id),
                FOREIGN KEY (produkt_id) REFERENCES xbyte_produkty(id)
            )
            """)
            conn.commit()
        
        return conn
    except mysql.connector.Error as err:
        print(f"Chyba připojení k databázi: {err}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
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
        
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return render_template('register.html')
            
        cursor = conn.cursor(dictionary=True)

        # Kontrola, zda uživatel již existuje
        cursor.execute("SELECT * FROM xbyte WHERE username = %s OR email = %s", (username, email))
        existing_user = cursor.fetchone()

        if existing_user:
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
                conn.commit()
                flash("Registrace úspěšná! Nyní se můžete přihlásit.", "success")
                cursor.close()
                conn.close()
                return redirect(url_for('login'))
            except mysql.connector.Error as err:
                flash(f"Chyba při registraci: {err}", "error")

        cursor.close()
        conn.close()

    return render_template('register.html')

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
            cursor.execute("SELECT * FROM xbyte WHERE email = %s", (email,))
            user = cursor.fetchone()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['email'] = user['email']
                session['firstname'] = user['firstname']
                session['lastname'] = user['lastname']
                flash("Přihlášení úspěšné!", "success")
                cursor.close()
                conn.close()
                return redirect(url_for('index'))
            else:
                flash("Neplatný email nebo heslo!", "error")
        except mysql.connector.Error as err:
            flash(f"Chyba při přihlášení: {err}", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('email', None)
    session.pop('firstname', None)
    session.pop('lastname', None)
    flash("Byli jste úspěšně odhlášeni.", "info")
    return redirect(url_for('index'))

@app.route('/produkty')
def produkty():
    try:
        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return render_template('produkty.html', produkty=[])
            
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM xbyte_produkty")
        produkty = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('produkty.html', produkty=produkty)
    except mysql.connector.Error as err:
        flash(f"Chyba při načítání produktů: {str(err)}", "error")
        return render_template('produkty.html', produkty=[])
    
@app.route('/moje-objednavky')
def moje_objednavky():
    # Kontrola, zda je uživatel přihlášen
    if 'user_id' not in session:
        flash("Pro zobrazení objednávek se musíte přihlásit!", "error")
        return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        if not conn:
            flash("Nelze se připojit k databázi!", "error")
            return render_template('moje_objednavky.html', objednavky=[])
            
        cursor = conn.cursor(dictionary=True)
        
        # Získání všech objednávek uživatele
        cursor.execute("""
            SELECT o.id, o.celkova_cena, o.datum_objednavky, 
                   COUNT(po.id) AS pocet_polozek
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

@app.route('/nastaveni', methods=['GET', 'POST'])
def nastaveni():
    # Kontrola, zda je uživatel přihlášen
    if 'user_id' not in session:
        flash("Pro přístup k nastavení se musíte přihlásit!", "error")
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        stare_heslo = request.form.get('stare_heslo')
        nove_heslo = request.form.get('nove_heslo')
        potvrzeni_hesla = request.form.get('potvrzeni_hesla')
        
        # Kontrola, že nové heslo a potvrzení se shodují
        if nove_heslo != potvrzeni_hesla:
            flash("Nové heslo a potvrzení hesla se neshodují!", "error")
            return redirect(url_for('nastaveni'))
        
        try:
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
            conn.commit()
            
            flash("Heslo bylo úspěšně změněno.", "success")
            cursor.close()
            conn.close()
            
        except mysql.connector.Error as err:
            flash(f"Chyba při změně hesla: {str(err)}", "error")
    
    return render_template('nastaveni.html')

@app.route('/kontakt')
def kontakt():
    return render_template('kontakt.html')

@app.route('/kosik')
def kosik():
    return render_template('kosik.html')

@app.route('/kontaktuj', methods=['POST'])
def kontaktuj():
    jmeno = request.form.get('jmeno')
    email = request.form.get('email')
    zprava = request.form.get('zprava')
    
    try:
        msg = Message('Nová zpráva z kontaktního formuláře',
                    sender=app.config['MAIL_USERNAME'],
                    recipients=['xbyteprojekt@seznam.cz'])
        msg.body = f"""
        Jméno: {jmeno}
        E-mail: {email}
        Zpráva:
        {zprava}
        """
        mail.send(msg)
        flash('Vaše zpráva byla úspěšně odeslána! Děkujeme za kontaktování.', 'success')
    except Exception as e:
        flash(f'Při odesílání zprávy došlo k chybě: {str(e)}', 'error')
    
    return redirect(url_for('kontakt'))

@app.route('/check-auth')
def check_auth():
    if 'user_id' in session:
        return jsonify({'authenticated': True})
    else:
        return jsonify({'authenticated': False})

@app.route('/place-order', methods=['POST'])
def place_order():
    # Kontrola, zda je uživatel přihlášen
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Pro dokončení objednávky se musíte přihlásit'
        })
    
    try:
        data = request.json
        cart_items = data.get('items', [])
        total_price = data.get('totalPrice', 0)
        
        if not cart_items:
            return jsonify({
                'success': False,
                'message': 'Košík je prázdný'
            })
        
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
            error_message = "Nedostatek zboží na skladě:<br>"
            for prod in insufficient_stock:
                error_message += f"- {prod['name']}: požadováno {prod['requested']} ks, skladem {prod['available']} ks<br>"
            
            return jsonify({
                'success': False,
                'message': error_message,
                'insufficientStock': insufficient_stock
            })
        
        # Vytvoření záznamu objednávky
        cursor.execute(
            "INSERT INTO xbyte_objednavky (user_id, celkova_cena) VALUES (%s, %s)",
            (session['user_id'], total_price)
        )
        conn.commit()
        objednavka_id = cursor.lastrowid
        
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
        <h3>Objednané položky:</h3>
        <p>{produkty_html}</p>
        <p><strong>Doprava:</strong> 99 Kč</p>
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
        <h3>Přehled objednaných položek:</h3>
        <p>{produkty_html}</p>
        <p><strong>Doprava:</strong> 99 Kč</p>
        <p><strong>Celková cena:</strong> {total_price} Kč</p>
        <p>O průběhu zpracování Vaší objednávky Vás budeme informovat.</p>
        <p>S pozdravem,<br>
        Tým xByte</p>
        """
        mail.send(msg_zakaznik)
        
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

if __name__ == '__main__':
    # Spustí aplikaci na adrese 0.0.0.0 (což znamená, že je dostupná ze všech IP adres)
    # a na portu 5000. Parametr debug=True znamená, že aplikace běží v režimu ladění,
    # což umožňuje automatické restartování aplikace při změnách v kódu a zobrazuje chybové hlášky.
    app.run(host='0.0.0.0', port=5000, debug=True)
