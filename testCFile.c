void foo(char* b);
void bar(char* f);
void foobar();

int main(int argc, char* argv[]) {
	int x = 5;
	int y = 6;
	int z = 7;
	
	if (x > 10) {
		int i;
		do {
			foo(argv[1]);
		}
		while(x < y);
	}
	//Not finding this foo??
	else if (y < 10) {
		switch(y) {
			case 1:
				break;
			case 2:
				break;
			case 3:
				break;
			case 6:
				foo(argv[1]);
			default:
				bar(argv[1]);
		}
	}
	else if (x > 10 && y < 10) {
		int i;
		for (i = 0; i < x; i++) {
			bar(argv[1]);
		}
	}
	else if ( (y > x || y > 1) && z == 1 ) {
		while(x < y) {
			bar(argv[1]);
			x++;
		}
	}
	else {
		bar(argv[1]);
	}

}

void foo(char* b) {
	(b[0] == 'a') ? foobar() : bar(b);
}

void bar(char* f) {
	foobar();
}

void foobar() {
	int vuln = 5;
}