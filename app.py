from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secret'  # session ke liye
app.config['UPLOAD_FOLDER'] = 'static/images'  # Product or shop images yahan save honge
# Admin Login Credentials
ADMIN_EMAIL = 'admin@artify.com'
ADMIN_PASSWORD = 'admin123'


# Database connection function
def get_db_connection():
    conn = sqlite3.connect('artify.db')
    conn.row_factory = sqlite3.Row
    return conn

# Home Page
@app.route('/')
def home():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products ORDER BY id DESC LIMIT 4').fetchall()
    blogs = conn.execute('SELECT * FROM blogs ORDER BY id DESC LIMIT 3').fetchall()
    conn.close()
    return render_template('home.html', products=products, blogs=blogs)


# Register Route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form['role']
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()

        # Save basic user info
        conn.execute('INSERT INTO users (role, name, email, password) VALUES (?, ?, ?, ?)',
                     (role, name, email, password))
        conn.commit()

        # Get new user_id
        user_id = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()['id']

        # If user is a shop owner, save extra info
        if role == 'shop_owner':
            mobile = request.form['mobile']
            bank_account = request.form['bank_account']
            ifsc = request.form['ifsc']
            pan = request.form['pan']
            shop_name = request.form['shop_name']
            shop_logo = request.files['shop_logo']

            logo_filename = secure_filename(shop_logo.filename)
            logo_path = 'images/' + logo_filename
            shop_logo.save(os.path.join('static', logo_path))

            conn.execute('''
                INSERT INTO shops (user_id, shop_name, shop_logo, mobile, bank_account, ifsc, pan)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, shop_name, logo_path, mobile, bank_account, ifsc, pan))
            conn.commit()

        conn.close()
        flash("Registration successful! Please login.")
        return redirect(url_for('login'))

    return render_template('register.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Admin login check
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['user_id'] = 0
            session['role'] = 'admin'
            session['name'] = 'Admin'
            return redirect(url_for('admin_dashboard'))

        # Check for regular user login
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password)).fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']

            print(" Login successful, role:", user['role'])  # Debug log

            if user['role'] == 'shop_owner':
                return redirect(url_for('artisan_dashboard'))
            elif user['role'] == 'buyer':
                return redirect(url_for('customer_dashboard'))
        else:
            flash("Invalid credentials.")
            return redirect(url_for('login'))

    return render_template('login.html')


# Artisan Dashboard Route
from flask import Flask, render_template, session, redirect, url_for
import os

@app.route('/artisan_dashboard')
def artisan_dashboard():
    if 'user_id' not in session or session.get('role') != 'shop_owner':
        return redirect(url_for('login'))

    conn = get_db_connection()

    # ✅ Get artisan info (from users table)
    artisan = conn.execute('SELECT email FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    # ✅ Get shop info (from shops table)
    shop = conn.execute('SELECT shop_name, shop_logo FROM shops WHERE user_id = ?', (session['user_id'],)).fetchone()

    # ✅ Get products
    products = conn.execute('SELECT * FROM products WHERE user_id = ?', (session['user_id'],)).fetchall()

    # ✅ Get orders
    orders = conn.execute('''
        SELECT o.*, p.name AS product_name
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE p.user_id = ?
    ''', (session['user_id'],)).fetchall()

    # ✅ Income calculation
    total_income = sum([order['total_price'] if 'total_price' in order.keys() else 0 for order in orders])
    profit = round(total_income * 0.90, 2)

    conn.close()

    # ✅ Handle shop_logo_url safely
    if shop and shop['shop_logo']:
        shop_logo_url = url_for('static', filename='images/' + os.path.basename(shop['shop_logo']))
    else:
        shop_logo_url = url_for('static', filename='images/default_logo.png')  # fallback image

    return render_template('artisan_dashboard.html',
                           artisan_name=shop['shop_name'] if shop else 'Artisan',
                           artisan_email=artisan['email'] if artisan else '',
                           shop_name=shop['shop_name'] if shop else '',
                           shop_logo_url=shop_logo_url,
                           products=products,
                           orders=orders,
                           total_orders=len(orders),
                           total_income=total_income,
                           profit=profit)
# Add Product Route (POST only — no HTML page!)
@app.route('/add_product', methods=['POST'])
def add_product():
    if 'user_id' not in session or session.get('role') != 'shop_owner':
        return redirect(url_for('login'))

    name = request.form['product_name']
    price = request.form['price']
    description = request.form['description']
    image_file = request.files['product_image']

    filename = secure_filename(image_file.filename)
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_file.save(image_path)

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO products (user_id, name, price, description, image)
        VALUES (?, ?, ?, ?, ?)
    ''', (session['user_id'], name, price, description, filename))
    conn.commit()
    conn.close()

    flash('Product added successfully!')
    return redirect(url_for('artisan_dashboard'))

# Admin Dashboard
@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return "Access Denied"
    return render_template('admin_dashboard.html')


# Customer Dashboard
@app.route('/customer/dashboard')
def customer_dashboard():
    if session.get('role') != 'buyer':
        return "Access Denied"

    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products').fetchall()

    # cart count
    cart_count = conn.execute('SELECT COUNT(*) as count FROM cart WHERE user_id = ?', 
                              (session['user_id'],)).fetchone()['count']
    conn.close()

    return render_template('customer_dashboard.html', products=products, cart_count=cart_count)




# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Admin - View all users
@app.route('/admin/users')
def view_users():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return render_template('admin_users.html', users=users)

# Admin - View all shops
@app.route('/admin/shops')
def view_shops():
    conn = get_db_connection()
    shops = conn.execute('SELECT * FROM shops').fetchall()
    conn.close()
    return render_template('admin_shops.html', shops=shops)

# Admin - View all products
@app.route('/admin/products')
def view_products():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products').fetchall()
    conn.close()
    return render_template('admin_products.html', products=products)

# Cart functionality
@app.route('/cart')
def view_cart():
    if 'user_id' not in session or session.get('role') != 'buyer':
        return redirect(url_for('login'))

    conn = get_db_connection()
    products = conn.execute('''
        SELECT p.*, c.id AS cart_id
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    ''', (session['user_id'],)).fetchall()

    total_price = sum([product['price'] for product in products])
    conn.close()

    return render_template('cart.html', products=products, total_price=total_price)


# add to cart
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if 'user_id' not in session or session.get('role') != 'buyer':
        return redirect(url_for('login'))

    conn = get_db_connection()

    # Check if already in cart
    existing = conn.execute('SELECT * FROM cart WHERE user_id = ? AND product_id = ?', 
                            (session['user_id'], product_id)).fetchone()

    if not existing:
        conn.execute('INSERT INTO cart (user_id, product_id) VALUES (?, ?)', 
                     (session['user_id'], product_id))
        conn.commit()

    conn.close()
    flash("Product added to cart.")
    return redirect(url_for('customer_dashboard'))

# remove from cart
@app.route('/remove_from_cart/<int:cart_id>')
def remove_from_cart(cart_id):
    if 'user_id' not in session or session.get('role') != 'buyer':
        return redirect(url_for('login'))

    conn = get_db_connection()
    conn.execute('DELETE FROM cart WHERE id = ? AND user_id = ?', (cart_id, session['user_id']))
    conn.commit()
    conn.close()

    flash("Item removed from cart.")
    return redirect(url_for('view_cart'))
# List all shops
@app.route('/shops')
def list_shops():
    conn = get_db_connection()
    shops = conn.execute('SELECT * FROM shops').fetchall()
    conn.close()
    return render_template('shops.html', shops=shops)


# View products of a specific shop
@app.route('/shops/<int:shop_id>')
def view_shop_products(shop_id):
    conn = get_db_connection()
    shop = conn.execute('SELECT * FROM shops WHERE id = ?', (shop_id,)).fetchone()
    products = conn.execute('SELECT * FROM products WHERE user_id = ?', (shop['user_id'],)).fetchall()
    conn.close()
    return render_template('shop_products.html', shop=shop, products=products)

  
# Admin - Add Workshop
@app.route('/admin/add_workshop', methods=['GET', 'POST'])
def add_workshop():
    if session.get('role') != 'admin':
        return "Access Denied"

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        date = request.form['date']
        time = request.form['time']
        location = request.form['location']
        image_file = request.files['image']

        filename = secure_filename(image_file.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image_file.save(image_path)

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO workshops (title, description, date, time, location, image)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, description, date, time, location, filename))
        conn.commit()
        conn.close()

        flash("Workshop added successfully!")
        return redirect(url_for('add_workshop'))

    return render_template('add_workshop.html')
# learn page route
@app.route('/learn')
def learn():
    conn = get_db_connection()
    workshops = conn.execute('SELECT * FROM workshops').fetchall()
    blogs = conn.execute('SELECT * FROM blogs').fetchall()
    videos = conn.execute('SELECT * FROM videos').fetchall()
    conn.close()

    return render_template('learn.html', workshops=workshops, blogs=blogs, videos=videos)


# Post Blog Route

@app.route('/post_blog', methods=['GET', 'POST'])
def post_blog():
    if 'user_id' not in session or session.get('role') != 'shop_owner':
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        image_file = request.files.get('image')
        image_filename = None

        if image_file and image_file.filename:
            image_filename = secure_filename(image_file.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            image_file.save(image_path)

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO blogs (user_id, title, content, image)
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], title, content, image_filename))
        conn.commit()
        conn.close()

        flash("Blog posted successfully!")
        return redirect(url_for('artisan_dashboard'))

    return render_template('post_blog.html')

# Upload Video Route
@app.route('/upload_video', methods=['GET', 'POST'])
def upload_video():
    if 'user_id' not in session or session.get('role') != 'shop_owner':
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        url = request.form['url']
        tags = request.form['tags']

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO videos (user_id, title, description, url, tags)
            VALUES (?, ?, ?, ?, ?)
        ''', (session['user_id'], title, description, url, tags))
        conn.commit()
        conn.close()

        flash("Video uploaded successfully!")
        return redirect(url_for('upload_video'))

    return render_template('upload_video.html')

# Blog id Detail Page
@app.route('/blog/<int:blog_id>')
def blog_detail(blog_id):
    conn = get_db_connection()
    blog = conn.execute('''
        SELECT b.*, u.name 
        FROM blogs b
        JOIN users u ON b.user_id = u.id
        WHERE b.id = ?
    ''', (blog_id,)).fetchone()
    conn.close()

    if blog is None:
        return "Blog not found", 404

    return render_template('blog_detail.html', blog=blog)

# Edit Product Route
# Edit Product Route
@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    # Ensure user is logged in and is a shop owner
    if 'user_id' not in session or session.get('role') != 'shop_owner':
        return redirect(url_for('login'))

    conn = get_db_connection()

    # Fetch the product owned by the logged-in artisan
    product = conn.execute('SELECT * FROM products WHERE id = ? AND user_id = ?', 
                           (product_id, session['user_id'])).fetchone()

    if not product:
        conn.close()
        return "Product not found or unauthorized", 404

    # Handle form submission
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        description = request.form['description']
        image = request.files.get('image')

        if image and image.filename:
            image_filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

            # Update with new image
            conn.execute('''
                UPDATE products 
                SET name = ?, price = ?, description = ?, image = ?
                WHERE id = ?
            ''', (name, price, description, image_filename, product_id))
        else:
            # Update without changing image
            conn.execute('''
                UPDATE products 
                SET name = ?, price = ?, description = ?
                WHERE id = ?
            ''', (name, price, description, product_id))

        conn.commit()
        conn.close()

        flash("✅ Product updated successfully!")
        return redirect(url_for('artisan_dashboard'))

    conn.close()
    return render_template('edit_product.html', product=product)
# My Orders Route

@app.route('/my_orders')
def my_orders():
    if 'user_id' not in session or session.get('role') != 'buyer':
        return redirect(url_for('login'))

    conn = get_db_connection()
    orders = conn.execute('''
        SELECT o.*, p.name AS product_name, p.image AS product_image, p.price
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.customer_id = ?
        ORDER BY o.timestamp DESC
    ''', (session['user_id'],)).fetchall()
    conn.close()

    return render_template('my_orders.html', orders=orders)

# Checkout Route
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session or session.get('role') != 'buyer':
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        name = request.form['customer_name']
        mobile = request.form['customer_mobile']
        address = request.form['customer_address']

        cart_items = conn.execute('''
            SELECT c.product_id, p.artisan_id
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = ?
        ''', (session['user_id'],)).fetchall()

        # Save each cart item as order
        for item in cart_items:
            conn.execute('''
                INSERT INTO orders (product_id, artisan_id, customer_id, customer_name, customer_mobile, customer_address)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                item['product_id'], item['artisan_id'], session['user_id'],
                name, mobile, address
            ))

        # Clear cart
        conn.execute('DELETE FROM cart WHERE user_id = ?', (session['user_id'],))
        conn.commit()
        conn.close()

        flash("Order placed successfully!")
        return redirect(url_for('my_orders'))

    # GET Request → show total price
    cart_items = conn.execute('''
        SELECT p.price FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    ''', (session['user_id'],)).fetchall()

    total_price = sum([item['price'] for item in cart_items])
    conn.close()

    return render_template('checkout.html', total_price=total_price)

# Buy Now Route
@app.route('/buy_now/<int:product_id>', methods=['GET', 'POST'])
def buy_now(product_id):
    if 'user_id' not in session or session.get('role') != 'buyer':
        return redirect(url_for('login'))

    conn = get_db_connection()

    # GET: Show checkout form for selected product
    if request.method == 'GET':
        product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
        conn.close()

        if not product:
            flash("Product not found.")
            return redirect(url_for('customer_dashboard'))
        
        return render_template('checkout.html', products=[product], total_price=product['price'], buy_now=True, product_id=product['id'])

        
    # POST: Place order directly
    customer_name = request.form['customer_name']
    customer_mobile = request.form['customer_mobile']
    customer_address = request.form['customer_address']
    transaction_id = request.form.get('transaction_id', 'N/A')

    # Fetch product & artisan info
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    artisan_id = product['user_id']

    conn.execute('''
        INSERT INTO orders (product_id, artisan_id, customer_id, customer_name, customer_mobile, customer_address, transaction_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        product_id,
        artisan_id,
        session['user_id'],
        customer_name,
        customer_mobile,
        customer_address,
        transaction_id
    ))

    conn.commit()
    conn.close()

    flash("✅ Order placed successfully!")
    return redirect(url_for('my_orders'))

# Pay via UPI Route
@app.route('/pay_upi', methods=['GET', 'POST'])
def pay_upi():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        session['customer_name'] = request.form.get('customer_name')
        session['customer_mobile'] = request.form.get('customer_mobile')
        session['customer_address'] = request.form.get('customer_address')

        # ✅ Save product_id if present (Buy Now)
        product_id = request.form.get('product_id')
        if product_id:
            session['product_id'] = int(product_id)

        return redirect(url_for('pay_upi', from_page='checkout'))

    from_page = request.args.get('from_page', 'checkout')
    return render_template('pay_upi.html', from_page=from_page)

# Confirm Payment Route
@app.route('/confirm_payment', methods=['POST'])
def confirm_payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    transaction_id = request.form.get('transaction_id')
    conn = get_db_connection()

    # ✅ If Buy Now
    if 'product_id' in session:
        product_id = session.get('product_id')
        product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
        artisan_id = product['user_id']

        conn.execute('''
            INSERT INTO orders (product_id, artisan_id, customer_id, customer_name, customer_address, customer_mobile, transaction_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            product_id,
            artisan_id,
            session['user_id'],
            session.get('customer_name'),
            session.get('customer_address'),
            session.get('customer_mobile'),
            transaction_id
        ))

        # ✅ Clear product_id from session
        session.pop('product_id', None)

    else:
        # ✅ Normal cart items
        cart_items = conn.execute('SELECT * FROM cart WHERE user_id = ?', (session['user_id'],)).fetchall()

        for item in cart_items:
            product = conn.execute('SELECT * FROM products WHERE id = ?', (item['product_id'],)).fetchone()
            artisan_id = product['user_id']

            conn.execute('''
                INSERT INTO orders (product_id, artisan_id, customer_id, customer_name, customer_address, customer_mobile, transaction_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['product_id'],
                artisan_id,
                session['user_id'],
                session.get('customer_name'),
                session.get('customer_address'),
                session.get('customer_mobile'),
                transaction_id
            ))

        conn.execute('DELETE FROM cart WHERE user_id = ?', (session['user_id'],))

    conn.commit()
    conn.close()

    # ✅ Clear customer details from session
    session.pop('customer_name', None)
    session.pop('customer_mobile', None)
    session.pop('customer_address', None)

    flash('✅ Payment successful! Order placed.')
    return redirect(url_for('my_orders'))
# cancel order route
@app.route('/cancel_order/<int:order_id>')
def cancel_order(order_id):
    if 'user_id' not in session or session.get('role') != 'buyer':
        return redirect(url_for('login'))

    conn = get_db_connection()

    order = conn.execute('SELECT * FROM orders WHERE id = ? AND customer_id = ?', (order_id, session['user_id'])).fetchone()

    if order and order['status'] in ('Pending', 'Confirmed'):
        conn.execute('UPDATE orders SET status = ? WHERE id = ?', ('Cancelled by Customer', order_id))
        conn.commit()
        flash('✅ Order cancelled successfully.')
    else:
        flash('⚠ Cannot cancel this order.')

    conn.close()
    return redirect(url_for('my_orders'))

@app.route('/update_order/<int:order_id>/<status>')
def update_order(order_id, status):
    if 'user_id' not in session or session.get('role') != 'shop_owner':
        return redirect(url_for('login'))

    status = status.strip().capitalize()
    print(f"Updating Order {order_id} to Status: {status}")

    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
    conn.commit()
    conn.close()

    flash(f"Order marked as {status}")
    return redirect(url_for('artisan_dashboard'))


@app.route('/delete_order/<int:order_id>')
def delete_order(order_id):
    if 'user_id' not in session or session.get('role') != 'shop_owner':
        return redirect(url_for('login'))

    conn = get_db_connection()
    conn.execute('DELETE FROM orders WHERE id = ?', (order_id,))
    conn.commit()
    conn.close()

    flash('❌ Order deleted successfully.')
    return redirect(url_for('artisan_dashboard'))

# ✅ This should come LAST
if __name__ == '__main__':
    app.run(debug=True)


