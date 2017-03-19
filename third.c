
int main(int ** argc , char* argv[])
{
function1(2,3);
function2(2,3);
int a, b, c;
b=a+1;

 
return 0 ;
}

void function1(int a,int b)
{
int k;
k=2;

}

void  function2(int a, int b)
{
function1(2,3);
int p;
p=2;
function3(2,3);
}


void  function3(int a, int b)
{
function1(2,3);
int p;
p=2;

}

