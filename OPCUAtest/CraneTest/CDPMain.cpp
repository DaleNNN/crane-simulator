#include <CDPStarter.h>
#include <Libraries.h>

/*!
DO NOT MODIFY - ONLY FOR ADVANCED USERS FOR VERY SPECIFIC TASKS.
IF YOU ARE NEW TO CDP STUDIO, GO TO HELP AND READ: A GETTING STARTED GUIDE.

This is the entry-point for the application.

It starts the CDP application, which uses the configuration along with the linked libraries
to generate and configure the application based on the configuration.

To edit the configuration, use Configure mode to add/remove/configure existing CDP objects.
To create a new CDP object, create a library (from Welcome mode) and write your logic into a component,
so it becomes a reusable resource for your system.
*/

int main (int argc, char* argv[])
{
    int ret = 0;
    CDPStarter CDPMain(argc, argv);
    if (!CDPMain.hasArgument("--help"))
    {
        ret = CDPMain.Start();
        printf("Good Bye!\n");
    }
    else
        CDPMain.PrintHelp();

    return ret;
}
