from __future__ import print_function
import sys, glob

# This is not required if you've installed pycparser into
# your site-packages/ with setup.py
sys.path.extend(['.', '..'])

importError = False;

try:
	from pycparser import c_parser, c_ast, parse_file
except ImportError:
	print("Please install PyCParser");
	importError = True;

try:
	import numpy as np
except ImportError:
	print("Please install numpy");
	importError = True;

try:
	import graphviz as gv
except ImportError:
	print("Please install GraphViz");
	importError = True;

try:
	import matplotlib.pyplot as plt
except ImportError:
	print("Please install MatPlotLib");
	importError = True;

if (importError):
	sys.exit(1);


methodQueue = [];		#Queue of tuples (methodName, methodNode) of methods we're tracing.  methodNode is the CFGNode of the method
rootNode 	= None;		#The root of our tree

funcCalls 	= {};		# FunctionName: [List of FuncCall nodes for that function]
						#Using a dictionary to keep track of function call nodes allows us to scale with size, rather than time
						#The problem with using this is that we can no longer get a parent tree, we would
						# need to find another way to deal with the upwards trace/parent links

astToCfg = {}	#Ast_Node:CFGNode, to keep track of existing AST_nodes

funcDefCFGNodes = {}	# FunctionName: CFGNode
globalNodeID = 0;

class CFGNode():
	"""
	Currently represents a function call
	Root node: function as "", parents as empty, children as not empty, and info as None
	'Root' is technically the vulnerable point we start at
	The exit nodes will have children as empty and parents as not
	"""
	def __init__(self, funcname, ast_info):
		self.function	= funcname;	#The name of the function this node represents
		self.parents 	= [];		#List of CFGNode that call this function (who calls this function)
		self.children 	= [];		#List of CFGNode called by this function (who this function calls)
		self.info 		= ast_info;	#Info about said node, most likely will be the actual AST node
		
		global globalNodeID;
		self.uniqueID	= str(globalNodeID);
		globalNodeID 	+= 1;

	def __repr__(self):
		return self.function;

	def __str__(self):
		return self.function;

	def add_child(self, child, duplicates=True):
		"""Add a child node to this node"""
		if (not duplicates and any(c.uniqueID == child.uniqueID for c in self.children)):
			pass;
		else:
			self.children.append(child);
			child.parents.append(self);
			#print("Adding %s (%s) to the tree as child of %s (%s)" % (child.function, child.uniqueID, self.function, self.uniqueID));

	def add_children_depth(self, children, duplicates=True):
		"""Adds a list of children vertically :: returns the last child in the list"""
		lastNode = self;
		for child in children:
			lastNode.add_child(child, duplicates=duplicates);
			lastNode = child;

		return lastNode;

	def print_tree(self, spaces):
		"""Textual version of the CFG from this node downward"""
		print(spaces*" " + self.__str__());	#2 spaces per level
		for child in self.children:
			child.print_tree(spaces + 2);


class FuncCallVisitor(c_ast.NodeVisitor):
	"""Used to interact with all FuncCall nodes"""
	def __init__(self, funcname, startingNode):
		"""Store information we'll need here"""
		self.funcname 		= funcname 			#The name of the function call nodes we are looking for
		self.currentCFGNode = startingNode;		#
		self.parentList = [];	#Keeps track of the list of nodes we've seen on this path in the AST (works b/c generic_visit is DFS)

	def visit_FuncCall(self, node):
		"""Triggers every time we find a FuncCall node in PyCParser's AST"""
		#If this node is of the function we are looking for
		if node.name.name == self.funcname:
			#Check if this method is already in the parent node's children, if so we don't need to add it again, if not add it
			#NOTE: We probably want to know all calls inside a method as well as the line numbers those calls are on
			if ( not any(x.function == node.name.name for x in self.currentCFGNode.parents) ):
				#self.currentCFGNode.add_parent( CFGNode(node.name.name, node) );
				
				#Upwards trace of c_ast nodes until we find the FuncDef that 'node' is inside of
				numberAboveCurrent = -1;
				isDefinedIn = self.parentList[numberAboveCurrent];
				conditionsAndLoops = [];	#Holds CFGNodes (in order) that represent if/else/switch/for/while.  If the entire list is false evaluations then this path is an else
				inIfRecurse = False;
				while (not isinstance(isDefinedIn, c_ast.FuncDef)):
					if (isinstance(isDefinedIn, c_ast.FileAST)):	#If we get to the top of the AST something really bad happened
						print("ERROR (FATAL): upward parent trace reached FileAST node");
						sys.exit();

					#Deals with if/else if[ else if [ else if...]]/else
					if (isinstance(isDefinedIn, c_ast.If)):
						isDefinedIn.show();
						#Get the BinaryOP and then the string representing it
						conditionResult = None;

						#Get the compound reperesenting the outcome of this if's flow that we came from
						ifCompound = self.parentList[numberAboveCurrent + 1];

						#If we're in an If recurse or the compound was the false part of the if/else, this must resolve to false
						if (inIfRecurse or ifCompound is isDefinedIn.iffalse):
							conditionResult = 1;

						#If the compound we just came form is 1st child, the if statement BinaryOp must be true
						elif (ifCompound is isDefinedIn.iftrue):
							conditionResult = 0;

						#Ensure we don't get a KeyError
						if (isDefinedIn not in astToCfg):
							astToCfg[isDefinedIn] = [None, None];

						#Make the new node if it doesn't already exist
						if (not astToCfg[isDefinedIn][conditionResult]):
							conditionString = resolveToString(isDefinedIn);
							newNode = None;
							if (conditionResult == 0):
								newNode = CFGNode(conditionString + " :: True", isDefinedIn);
							else:
								newNode = CFGNode(conditionString + " :: False", isDefinedIn);
							astToCfg[isDefinedIn][conditionResult] = newNode;
							
						conditionsAndLoops.append(astToCfg[isDefinedIn][conditionResult]);

						#Indicate we may be in an upwards recusive if/else if/else tree
						inIfRecurse = True;

					#TODO: Logic for dealing with switch statements goes here
					elif (isinstance(isDefinedIn, c_ast.Switch)):
						#isDefinedIn.cond is the BinaryOp object
						inIfRecurse = False;

						#Resolve our strings
						switchString = resolveToString(isDefinedIn);
						
						#If we already have a CFGNode for this ast_node use it, don't make a new one
						newNode = None;
						try:
							newNode = astToCfg[isDefinedIn];
						except KeyError:
							newNode = CFGNode(switchString, isDefinedIn);
							astToCfg[isDefinedIn] = newNode;
							
						conditionsAndLoops.append(newNode);

					#This should always be hit before the above Switch elif
					elif (isinstance(isDefinedIn, c_ast.Case)):
						caseString = resolveToString(isDefinedIn);

						#If we already have a CFGNode for this ast_node use it, don't make a new one
						newNode = None;
						try:
							newNode = astToCfg[isDefinedIn];
						except KeyError:
							newNode = CFGNode(caseString, isDefinedIn);
							astToCfg[isDefinedIn] = newNode;
							
						conditionsAndLoops.append(newNode);

						inIfRecurse = False;

					#For loop
					elif (isinstance(isDefinedIn, c_ast.For)):
						inIfRecurse = False;
						forString = resolveToString(isDefinedIn);

						#If we already have a CFGNode for this ast_node use it, don't make a new one
						newNode = None;
						try:
							newNode = astToCfg[isDefinedIn];
						except KeyError:
							newNode = CFGNode(forString, isDefinedIn);
							astToCfg[isDefinedIn] = newNode;
							
						conditionsAndLoops.append(newNode);

					#While loop
					elif (isinstance(isDefinedIn, c_ast.While)):
						inIfRecurse = False;
						whileString = resolveToString(isDefinedIn);

						#If we already have a CFGNode for this ast_node use it, don't make a new one
						newNode = None;
						try:
							newNode = astToCfg[isDefinedIn];
						except KeyError:
							newNode = CFGNode(whileString, isDefinedIn);
							astToCfg[isDefinedIn] = newNode;
							
						conditionsAndLoops.append(newNode);

					#DoWhile loop
					elif (isinstance(isDefinedIn, c_ast.DoWhile)):
						inIfRecurse = False;
						doWhileString = resolveToString(isDefinedIn);

						#If we already have a CFGNode for this ast_node use it, don't make a new one
						newNode = None;
						try:
							newNode = astToCfg[isDefinedIn];
						except KeyError:
							newNode = CFGNode(doWhileString, isDefinedIn);
							astToCfg[isDefinedIn] = newNode;
							
						conditionsAndLoops.append(newNode);

					elif (isinstance(isDefinedIn, c_ast.TernaryOp)):
						inIfRecurse = False;

						ternaryString = resolveToString(isDefinedIn);

						#If we already have a CFGNode for this ast_node use it, don't make a new one
						newNode = None;
						try:
							newNode = astToCfg[isDefinedIn];
						except KeyError:
							newNode = CFGNode(ternaryString, isDefinedIn);
							astToCfg[isDefinedIn] = newNode;
							
						conditionsAndLoops.append(newNode);

					else:
						inIfRecurse = False;

					numberAboveCurrent -= 1;
					isDefinedIn = self.parentList[numberAboveCurrent];

				#Get the name and location of the function we are in
				methodName = isDefinedIn.decl.name;
				methodLocation = isDefinedIn.decl.coord;

				#Something really bad happened for us to not find the name for this FuncDef node
				if (methodName is None):
					print("ERROR (FATAL): unable to locate function name holding call to " + self.funcname);
					sys.exit();

				newNode = None;
				if (methodName in funcDefCFGNodes.keys()):
					newNode = funcDefCFGNodes[methodName];

				#Make a CFG node for this "new" node, and add it to the methodQueue only if it is not already in the methodQueue
				if (not any(entry[0] == methodName for entry in methodQueue) ):
					if (newNode is None):
						newNode = CFGNode(methodName, isDefinedIn);			#Make the new CFGNode
						funcDefCFGNodes[methodName] = newNode;
						astToCfg[isDefinedIn] = newNode;

					#Add the list of conditionals if we need to
					lastNode = self.currentCFGNode.add_children_depth(conditionsAndLoops, duplicates=False);
					lastNode.add_child(newNode, duplicates=False);				#Add the new CFGNode as a child of the current CFGNode
					methodQueue.append( (methodName, newNode) );		#Add the method we found it in to the methodQueue
				else:
					#Add the list of conditionals if we need to
					lastNode = self.currentCFGNode.add_children_depth(conditionsAndLoops, duplicates=False);
					lastNode.add_child(funcDefCFGNodes[methodName], duplicates=False);

		#Visit all children of this node
		FuncCallVisitor.generic_visit(self, node);

	def generic_visit(self, node):
		"""Overrides the standard generic_visit method to keep track of the parent listings,
		   which are accessed while traversing"""

		#We are about to move down another level, so add this node to the parentList
		self.parentList.append(node);
		
		#Go through all of this node's children
		for c_name, c in node.children():
			self.visit(c);

		#We just finished all children, and are about to move up a level, so remove this node from the parentList
		self.parentList.pop(-1);


class LineNumberVisitor(c_ast.NodeVisitor):
	"""This class' sole purpose is to find the first c_ast node on a certain line number"""

	def __init__(self, linenumber, file):
		self.lineno 	= linenumber;	#The line number we are looking for
		self.fileName 	= file;			#The file in which we are looking for
		self.ast_node 	= None;			#The node found on the specified linenumber
		self.lastFuncDefName = None;	#The name of the function this line number is inside of
		self.lastFuncDefNode = None;	#The FuncDef node this line number is inside of

	def generic_visit(self, node):
		"""Overrides the standard generic_visit to find the node on the specified line number"""

		#We found our node on the line, don't do anything more
		if (self.ast_node is not None):
			return;

		#
		if (isinstance(node, c_ast.FuncCall)):
			global funcCalls;
			if (node.name not in funcCalls.keys()):
				funcCalls[node.name] = []
			funcCalls[node.name].append(node);

		#We will never need to find the FileAST node
		if (not isinstance(node, c_ast.FileAST)):
			#Keeps track of the function we are currently inside of
			if (isinstance(node, c_ast.FuncDef)):
				self.lastFuncDefNode = node;

				#Find the name of the function (based on the above processing) that 'node' is inside of
				for c_name, child in node.children():	#Now we have the FuncDef node of the method we are in
					if (isinstance(child, c_ast.Decl)):			#Found where the node's name is stored
						self.lastFuncDefName = child.name;
						break;

			#Don't do anything if we've already found a node on that line number
			if (self.ast_node is not None):
				return;

			#Figure out if we have a node from that line number
			lineNumber 	= node.coord.line;
			nodeFile 	= node.coord.file;
			if (lineNumber is not None and lineNumber == self.lineno and nodeFile == self.fileName):
				self.ast_node = node;
				return;

		#If this node didn't give us the line number, go to all its children
		if (self.ast_node is None):
			for c_name, c in node.children():
				self.visit(c);



def resolveToString(node):
	"""Takes the PyCParser node and returns a string representation of it"""
	#TODO: the better way to do this would be by anonymous function
	#		the methods would be toStringNODECLASS(node):
	#		You'd simply append the name of the node class to 'toString' and call it, no giant if/elif need
	#TODO: only include the nodes we actually need (or not, as we don't know what we'll need)
	#NOTE: Even easier would be if these classes just had a damn __str__ method!!!!!!!!

	#ArrayDecl
	#ArrayRef
	if (isinstance(node, c_ast.ArrayRef)):
		name = resolveToString(node.name);
		subscript = resolveToString(node.subscript);
		return (name + '[' + subscript + ']');
	#Assignment
	if (isinstance(node, c_ast.Assignment)):
		assign = str(node.op);
		lval = str(resolveToString(node.lvalue));
		rval = str(resolveToString(node.rvalue));
		return (lval + assign + rval);
	#BinaryOp
	if (isinstance(node, c_ast.BinaryOp)):
		string = node.op;

		#If the child is a BinaryOP we need to recurse again
		if (isinstance(node.left, c_ast.BinaryOp)):
			string = ('(' + resolveToString(node.left) + " " + string);
		else:
			string = ('(' + resolveToString(node.left) +  " " + string);

		if (isinstance(node.right, c_ast.BinaryOp)):
			string += (" " + resolveToString(node.right) + ')');
		else:
			string += (" " + resolveToString(node.right) + ')');

		return string;
	#Break
	#Case
	if (isinstance(node, c_ast.Case)):
		return ("case " + resolveToString(node.expr));
	#Cast
	#Compound
	if (isinstance(node, c_ast.Compound)):
		print("ERROR: we should never be resolving 'Compound' to a string");
		return;
	#CompoundLiteral
	#Constant
	if (isinstance(node, c_ast.Constant)):
		return (node.value);
	#Continue
	#Decl
	#DeclList
	#Default
	#DoWhile
	if (isinstance(node, c_ast.DoWhile)):
		cond = resolveToString(node.cond);
		return ("DoWhile (" + cond + ')');
	#EllipsisParam
	#EmptyStatement
	#Enum
	#Enumerator
	#EnumeratorList
	#ExprList
	if (isinstance(node, c_ast.ExprList)):
		ret = "";
		for expr in node.exprs:
			ret += (', ' + resolveToString(expr));

		return ret[2:];
	#FileAST
	#For
	if (isinstance(node, c_ast.For)):
		init = resolveToString(node.init);
		cond = resolveToString(node.cond);
		nxt = resolveToString(node.next);
		return ("for (" + init + "; " + cond + "; " + nxt + ")");
	#FuncCall
	if (isinstance(node, c_ast.FuncCall)):
		name = resolveToString(node.name);
		args = resolveToString(node.args);
		return (name + '(' + ( args if args else '' ) + ')');
	#FuncDecl
	#FuncDef
	#Goto
	if (isinstance(node, c_ast.Goto)):
		return ("Goto " + resolveToString(node.name));
	#ID
	if (isinstance(node, c_ast.ID)):
		return node.name;
	#IdentifierType
	#If
	if (isinstance(node, c_ast.If)):
		cond = resolveToString(node.cond);
		return ("if " + cond);
	#InitList
	#Label
	#NamedInitializer
	#ParamList
	#PtrDecl
	#Return
	#Struct
	#StructRef
	#Switch
	if (isinstance(node, c_ast.Switch)):
		cond = resolveToString(node.cond);
		return ("switch (" + cond + ')');
	#TernaryOp
	if (isinstance(node, c_ast.TernaryOp)):
		cond = resolveToString(node.cond);
		iftrue = resolveToString(node.iftrue);
		iffalse = resolveToString(node.iffalse);
		return (cond + ' ? ' + iftrue + ' : ' + iffalse);
	#TypeDecl
	#Typedef
	#Typename
	#UnaryOp
	if (isinstance(node, c_ast.UnaryOp)):
		op = str(node.op);
		expr = resolveToString(node.expr);
		return (expr + op[1:]);
	#Union
	#While
	if (isinstance(node, c_ast.While)):
		cond = resolveToString(node.cond);
		return ("while (" + cond + ')');
	#Pragma
	if (isinstance(node, c_ast.Pragma)):
		return ("pragma " + node.string);


#
#For each methodName, methodNode in methodQueue:
#	Find each instance of the function call, put those in a queue
#	For each instance, find what function that call is inside of
#Repeat these steps using the new function each time until we reach main on all instances
#
def parseForCFG(filename, lineNo):
	"""Parse the file filename for a Control Flow Graph starting at lineNo"""

	#TODO: need to get this working with multiple C files
	'''
	#The root of the ast
	ast = FileAst();

	#Add to the overall AST each smaller AST file by file (recursing into all lower directories)
	for f in glob.iglob('**/*.c', recursive=True):
		ast.ext += CParser.parse_file(f, use_cpp=True).ext;
	'''

	#Create the AST to parse
	ast = parse_file(filename, use_cpp=True);

	#Given the line number, find the node of that line number
	lnv = LineNumberVisitor(lineNo, filename);
	lnv.visit(ast);
	vulnerableNode = lnv.ast_node;	#The node on the specified line
	if (vulnerableNode == None):
		print("ERROR (FATAL): unable to retrieve node for line " + str(lineno));
		sys.exit();
	
	global rootNode;
	rootNode = CFGNode("Line " + str(lineNo), None);
	lineFuncNode = CFGNode(lnv.lastFuncDefName, lnv.lastFuncDefNode);
	rootNode.add_child(lineFuncNode);

	#Add those to the methodQueue
	methodQueue.append( (lnv.lastFuncDefName, lineFuncNode) );

	#Parse continually while we have methods to look for in the methodQueue
	v = FuncCallVisitor('', None);
	while (methodQueue):
		methodName, methodNode = methodQueue.pop(0);
		v.funcname = methodName;
		v.currentCFGNode = methodNode;
		v.parentList = [];
		v.visit(ast)

	print();
	print();
	rootNode.print_tree(0);

	return rootNode;


def visualize(fileName, rootNode, direction, strict=False):
	"""Plots the tree starting at 'rootNode' is a visually pleasing format using GraphViz
		fileName: the name of the file in which the visual of the graph will be stored
		rootNode: the start of the graph to visualize
		direction: do we display from start->vulnerability (0) or vulnerability->start (1)?
	"""
	G = gv.Digraph('G', filename=fileName);

	stack = [rootNode];
	G.node(rootNode.uniqueID, rootNode.function);
	while (stack):
		curr_node = stack.pop(0);

		#Add a link from parent to child
		for child in curr_node.children:
			stack.append(child);

			#To go from start of program to vulnerable point swap these two arguments
			#print("Adding edge between %s (%s) and %s (%s)" % (child.function, child.uniqueID, curr_node.function, curr_node.uniqueID))
			G.node(child.uniqueID, child.function);
			if (direction == 0):
				G.edge(child.uniqueID, curr_node.uniqueID);
			elif (direction == 1):
				G.edge(curr_node.uniqueID, child.uniqueID);
			else:
				print("ERROR: incorrect direction to visualize: " + str(direction));
				print("\tDirection should be 0 or 1");
				return;

	G.view();



def visualizeAST(rootNode, fileName):
	G = gv.Digraph('G', filename=("AST" + fileName));

	stack = [rootNode];
	while (stack):
		curr_node = stack.pop(0);
		nodeName1 = curr_node.__class__.__name__;
		if (curr_node.attr_names):
			vlist = [getattr(curr_node, n) for n in curr_node.attr_names]
			attrstr = ', '.join('%s' % v for v in vlist)
			nodeName1 += (': ' + attrstr);
		
		for c, child in curr_node.children():
			stack.append(child);

			nodeName2 = child.__class__.__name__;
			if (child.attr_names):
				vlist = [getattr(child, n) for n in child.attr_names]
				attrstr = ', '.join('%s' % v for v in vlist)
				nodeName2 += (': ' + attrstr);
			G.edge(nodeName1, nodeName2);

	G.view();


if __name__ == "__main__":
	try:
		#TODO: take in another optional argument, the place we end the search at (either line number or function name)
		#		This allows us to find flows from line# to line # or function to function
		if len(sys.argv) == 3:	#programName filename linenumber
			filename = sys.argv[1];
			try:
				lineno = int(sys.argv[2]);
			except ValueError:
				print("LineNumber should be an integer");
				sys.exit();
		else:
			filename = 'third.c';
			lineno = 41;

		print("FileName: " + filename);
		print("LineNo: " + str(lineno));

		CFG = parseForCFG(filename, lineno)
		visualize(filename + "DOT", CFG, 0, strict=True);
	except KeyboardInterrupt:
		exit();