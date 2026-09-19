# Session file (i.e jsonl) is an append only. It is not flat array rather a tree meaning multiple branch can coexist
# when rewinding or forking. Leaf id is in memory pointer to the entry which is tip of the current active branch
# Eg: Suppose following entires exist on disk
# E1 (id: 1, parentId: null)
# E2 (id: 2, parentId: 1)
# E3 (id: 3, parentId: 2)
# Here leaf id is "3" so walking backwards via parentId resolves to [E1, E2, E3]
# Suppose you run /rewind to E1
# We will move in memory leafid pointer to 1 (leafid = "1")
# Now the active branch from leafid = "1" is just [E1]
# When we send new prompt E4, it is appended with parentId = leafid ("1")
# Then we will update leafid to "4"
# The file on disk is [E1, E2, E3, E4]
# Walking backwards from leafId = "4" will resolves to [E1, E4]
# 
# Lifecycle of LeafId:
#   - On file load leafId is initialized to last entry in the file
#   - On append (ie inserting new entry) leafId updates to newly appended entry ID
#   - On rewind/branch: leafId is assigned to the target entry ID
