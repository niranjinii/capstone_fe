from flask import Flask
app = Flask(__name__)

@app.route('/test')
def test():
    return "original"

def test_new():
    return "new"

app.view_functions['test'] = test_new

if __name__ == '__main__':
    with app.test_client() as c:
        print(c.get('/test').text)
