# Raw Prompts Archive

## Prompt 001 - 2026-05-10 - Initial Project Setup & 7 Scripts

```
Firstly lets get acccess out the way. You are allowed full file acccess, git:* an bash:*
Use automode an ddream mode

AGENTS
Architect (Opus)
repoter (hauku)
product owner (opus)
Sub agents (sonnet6) if need for more complex tasks refer to architect to break down further


Each agent should have enough information and context though to do their piece of work without
impacting the others. The orchestrator can keep record of this as well as dependancies.

It might be worth loking at minimizing tokens by saving this in an SQL light store and just
uupdating and querying from there. Types would be Phases, tasks, subtasks. Assigning each angent
as non blocking as possible and also creating context of the progran status of what needs to be
done vs what is outstanding. Any issues encountered, new patterns or faulty agents can be stored
for you to learn. This is totally up to you.

Please keep a copy of my raw prompts in claudfiles/prompts/rawprompts.md
Then help teach and me and adjust how I prompt by running his though haiku
giving me critical critique claudfiles/prompts/LearnToprompts.md showing me where
I went wrong and then corecting it for the next LLM. Scopre my propts out of 10

I then want you to create a folder called /claudefiles/files/thinkLikeMe.md where
you show the full thinking and reasonning you are following using mermaid files to do so.
Also create csv of architexture decisios if you know or dvided on something
/claudefiles/files/decision records. You will keep a an append only changelog
here /claudefiles/files/changelog.md

I would like you to turn on dreamand automode as well as other helpful claude tools to make this efficient.
You will.. start off having an architect I will give infomration to and then that will break this into
phases and tasks and subtasks. The Orchestrator an architect must communicate and make
sure enoug conext is known to competea a path

Aagent to agent chat is allowed to improve on items and when the phases, tasks, subtasks are done
they are appended only to the reporter (uses haiku) to save into the changelog.

Build context that can be shared amount the agents an something another angent can always
query for more information then when done report back to the orchestrator for updates.

Any new patterns of skills, agents or snapshots should be note, written in
/claudefiles/learnt/writeup of sckill, slash command and agent (simply what it does and the name.
TThe actual skill, agent and slash command can be written firectly to the file.

WWe are aiming to make short lived tasks not long ones, quick itterations.

Obecause this is production stae, commit and create a PR for changes after the inisial set.

Requirement

Golden rules:
1) maintain scruture of github when downloading something
2) write a comprehensive -h / --help manual with example. if the uer runs the
terminal tell them what this tool does and how to use it.
if they need help they can run the command -i /--interactive that will ask questions and then
send the query
3) Unless other save it to the direcory is it queries from with a date time stamp and Github_visibility.csv.
4) allow querying using the - -- notation along eitherh options available
5) stamp it and written by h3nryza
6) Ue the oproptiate language
7) where python/python3 is required build a enable and disable environment.
8) always allow he use to run this script remotely vur curl or GH and not have to clone this
9) give a name to the scripts,meaningful and keep all their files in there
10) use easy tu undersand function names
11) keep it simple DDD and TFF
12) write mock and unit tests incase needed


Scrip one
I need scripts to check the enterprise, org, owner has made it public or not in a CSV Ent, Org, User, visibility.
Unless other save it to the direcory is it queries from with a date time stamp and Github_visibility.csv.
allow querying any one of them with th - -- notation along eith import and export
I then need a way to buld make them public private or internal uploading the excel sheel with
the requirement. Pllease allow this with a GH account or via curl with PAT or gthub ouath app

script 2
TThen I need a script to download all information from an enterprise, enumerating an org and
then user for backup. I want to be able to target just a enterprise, or an org or a user.
This needs to maintain consistency of the structure including gists.
I would need an index.md with description if there is a description and a more detailed
csv or Ent, Org, User, Gist.
Unless other save it to the direcory is it queries from with a date time stamp and Github_visibility.csv.
allow querying any one of them with th - -- notation along eith import and export

script 3
following script 2 I would need to be able to move accounts acount my orgs NOT my enterprise by
uuploading the changes and only the repos to be changed and require feedback in csv on success or not.
I should be able to do this individually or import a sheet that shows the new owner. you can query github
and then simply if owners are change change it. bulk or singl migration (I have admin permissions

script 4
I have some github repositories being created and organizations an don't always get notfied about it.

could you build something that local in a venv environent as well as lambda where I give you the topeven
enterprize with an Oauth app and you enumerate down to the org, account and tell me what is
newly created?
build for lambda and local remote run, if local or lambda, output local if local, S3 location if labda

sscript 5
Wwe have a secuity problem where people are not using our reusable pipeline. I would like to view across the org
who is and is not using it, local or lambda, output local if local, S3 location if lambda.
The idea is to see the security posture across the estate, It ust also be able to find other files of patterns,
uuse - -- notation where possible and make your life more easy. I still want this built but can you tell
eme i a henrysexlaination.md in the document how to automatically install it?

SScript 6
TSame problem as $5, github best practises are not being followed for enterprises and enrollent policies fail.
II would like to create a comprehensive github atuomatedd checkup against best practises but also have an ecel sheet I can add my own
and pass through you to check. This is probably the most difficult one and will take time. go cllect all the data
for best practises on Enterprises, orgs, repos and anythig underneath (includin te .gitignore's) that
should be checked. It can run again as a lambda or local but keep the best practise file with you as imput.
Make sure to cover the SANS and OWASP and CIS benchmarks so we cna determine what we need again use the - -- notation
ffor the targets allow or to local, with pat or github app and also local file state if I download them

Script 7
II use github actions, terraform wth all providers and modules and git tells me to tag to
the hash of he release. how do i convert from the hash to a release and release to a hash?
I have a security dashboard and need to know if they on current, M-1, N-1 or lower.
If we have an index of our estate or look at the pipeline and artefacts I would like it to
ideally show as version and not hash.

Here I would like a personal and business function to put in an item or code/modue etc and ask for the versions.
In reality it will come though.a lambbda pipeline with all the lookups that need to be done
bboth internally and externally. This will run thorugh lambda with an output bucket and any artifact repositories internally.

I need to kow what fomat is expected in the secrets field and how it works so forward engineeringn is relese version to nuber (tag)
and reverse is tag/release number to tag

Please document these script with a summary, how to use and with examples and why use them.
please also document how you use the top github app and drill down to get the other ones info.
One of the issues I'm seeing is a manditory installation of my app not happening, any advise and documention
you can share on this is great

instead of one big cli tool break these up indipendantly and soe with be bash, other python and
some will become labda's others will stay purely informational.

don't forget to check yourself, loop and confirm peer to peer it is done, 2 peers need to review the one log.
I and one needs to test. I would like to see how this is done visually by you saving and exlaining it to me using mermaid diagrams and simpe to
understand and reasonanle tems under /claudefiles/files/tasksfolows.md I would love to kow where the context is being
gathered and saved but you can put this in index.md showing all the repos.
lastl I want to see what lessons we have learnt, agents. any new skill needs to the places in teh right directory, evry slash command
aand context to this repo (please advise where it is) Just append to the file to save tokens.
any valid patterns or anti valid should be named as such in /claudefiles/files/{}.md

lWrite up the readme with a paragraph for eac toolset, then within that roolset have the how to
run me. anyone with access should be able o run the command and not have to run the whol repo, either with curl, github app to gh, so how this
ccan be done on each tools side and explain on the front NOT to clone this.
```
