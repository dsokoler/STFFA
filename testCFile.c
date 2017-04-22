void foo(char* b);
void bar(char* f);
void foobar();

int main(int argc, char* argv[]) {
	int x = 5;
	int y = 6;
	int z = 7;
	
	if (x > 10) {
		int i;
		for (i = x; i < z; i--) {
			foo(argv[1]);
		}
	}
	//Not finding this foo??
	else if (y < 10) {
		foo(argv[1]);
	}
	else if (x > 10 && y < 10) {
		bar(argv[1]);
	}
	else if ( (x > 10 || y > 1) && z == 1 ) {
		bar(argv[1]);
	}
	else {
		bar(argv[1]);
	}

}

void foo(char* b) {
	foobar();
}

void bar(char* f) {
	foobar();
}

void foobar() {
	int vuln = 5;
}