using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

namespace Maps.MapAssembler
{
    /// <summary>
    ///     OptimizedMeshMapAssembler is an implementation of MapAssembler that assembles the maps using meshes.
    /// </summary>
    public class OptimizedMeshMapAssembler : MapAssembler
    {
        [SerializeField] private bool hasCeiling;

        [Header("Mesh materials")] [SerializeField]
        private Material topMaterial;

        [SerializeField] private Material wallMaterial;
        [SerializeField] private Material floorMaterial;
        
        private MeshCollider floorCollider;
        private MeshFilter floorMeshFilter;
        private GameObject navMeshObject;

        private MeshCollider topCollider;
        private MeshFilter topMeshFilter;
        private GameObject walls;

        private void Start()
        {
            GameObject childObject;

            childObject = new GameObject("Top - Mesh Filter");
            childObject.transform.parent = transform;
            childObject.transform.localPosition = Vector3.zero;
            topMeshFilter = childObject.AddComponent<MeshFilter>();
            childObject.AddComponent<MeshRenderer>();
            childObject.GetComponent<MeshRenderer>().material = topMaterial;

            walls = new GameObject("Walls");
            walls.transform.parent = transform;
            walls.transform.localPosition = Vector3.zero;
            walls.isStatic = true;

            if (hasCeiling)
            {
                childObject = new GameObject("Top - Collider");
                childObject.transform.parent = transform;
                childObject.transform.localPosition = Vector3.zero;
                topCollider = childObject.AddComponent<MeshCollider>();
            }

            childObject = new GameObject("Floor");
            childObject.transform.parent = transform;
            childObject.transform.localPosition = Vector3.zero;
            floorCollider = childObject.AddComponent<MeshCollider>();
            floorMeshFilter = childObject.AddComponent<MeshFilter>();
            childObject.AddComponent<MeshRenderer>();
            childObject.GetComponent<MeshRenderer>().material = floorMaterial;
            childObject.isStatic = true;
            childObject.layer = LayerMask.NameToLayer("Floor");
            SetReady(true);

            navMeshObject = new GameObject("NavMeshSurface");
            navMeshObject.transform.parent = transform;
            navMeshObject.transform.localPosition = Vector3.zero;
        }
        
        // Generates the Mesh.
        public override void AssembleMap(char[,] map, char wallChar, char roomChar)
        {
            CreateTopMesh(map.GetLength(0), map.GetLength(1));

            CreateWalls(map, wallChar);

            CreateFloorMesh(map.GetLength(0), map.GetLength(1));

            var navMesh = navMeshObject.AddComponent<NavMeshSurface>();
            navMesh.useGeometry = NavMeshCollectGeometry.PhysicsColliders;
            navMesh.layerMask = LayerMask.GetMask("Wall", "Floor");
            navMesh.overrideVoxelSize = true;

            var biggestSize = Mathf.Max(map.GetLength(0), map.GetLength(1)) * mapScale;

            if (biggestSize < 200)
            {
                navMesh.voxelSize = 4f/30f;
            }
            else // if (biggestSize < 400)
            {
                navMesh.voxelSize = 6f/30f;
            }
            // else if (biggestSize < 600)
            // {
                // navMesh.voxelSize = 8f/30f;
            // }
            // else
            // {
                // navMesh.voxelSize = 10f/30f;
            // }
            
            navMesh.BuildNavMesh();
        }

        public override void AssembleMap(
            List<char[,]> maps,
            char wallChar,
            char roomChar,
            char voidChar
        )
        {
        }

        // Creates the top mesh.
        private void CreateTopMesh(int rows, int columns)
        {
            if (hasCeiling)
            {
                var ceilingMesh = CreateRectangularMesh(rows, columns, mapScale, wallHeight, false);
                topMeshFilter.mesh = ceilingMesh;
            }
        }

        private readonly struct RowWalls
        {
            public readonly float row;
            public readonly float startingColumn;
            public readonly float endingColumn;
            // public readonly bool requiresClockwise;

            public RowWalls(float row, float startingColumn, float endingColumn/*, bool requiresClockwise*/)
            {
                this.row = row;
                this.startingColumn = startingColumn;
                this.endingColumn = endingColumn;
                // this.requiresClockwise = requiresClockwise;
            }
        }

        private readonly struct ColumnWalls
        {
            public readonly float column;
            public readonly float startingRow;
            public readonly float endingRow;
            // public readonly bool requiresClockwise;

            public ColumnWalls(float column, float startingRow, float endingRow/*, bool requiresClockwise*/)
            {
                this.column = column;
                this.startingRow = startingRow;
                this.endingRow = endingRow;
                // this.requiresClockwise = requiresClockwise;
            }
        }
        
        // Creates the wall mesh.
        private void CreateWalls(char[,] map, char wallChar)
        {
            var rows = map.GetLength(0);
            var columns = map.GetLength(1);

            var rowWalls = new List<RowWalls>();
            var columnWalls = new List<ColumnWalls>();
            
            // Build walls for rows
            for (var r = 1; r < rows; r++)
            {
                var c = 0;
                while (c < columns)
                {
                    if (map[r, c] != map[r - 1, c] && (map[r,c] == wallChar || map[r-1,c] == wallChar))
                    {
                        // var isWallInLowestRow = map[r - 1, c] == wallChar; 
                        var startingColumn = c;
                        c++;
                        while (c < columns && map[r, c] != map[r - 1, c] && (map[r,c] == wallChar || map[r-1,c] == wallChar)/* && !isWallInLowestRow ^ (map[r-1,c] == wallChar)*/)
                        {
                            c++;
                        }

                        rowWalls.Add(new RowWalls(mapScale * (rows - r), mapScale * startingColumn, mapScale * c/*, isWallInLowestRow*/));
                    }
                    else
                    {
                        c++;
                    }
                }
            } 
            
            // Build walls for columns
            for (var c = 1; c < columns; c++)
            {
                for (var r = 0; r < rows; r++)
                {
                    if (map[r, c] != map[r, c-1] && (map[r,c] == wallChar || map[r,c-1] == wallChar))
                    {
                        var startingRow = r;
                        r++;
                        while (r < rows && map[r, c] != map[r , c - 1] && (map[r,c] == wallChar || map[r,c - 1] == wallChar))
                        {
                            r++;
                        }
                        columnWalls.Add(new ColumnWalls(mapScale * c, mapScale * (rows - startingRow), mapScale * (rows - r)));
                    }
                }
            }
            
            // Build wall mesh. Even if using a MeshCollider, this is already much more optimized.

            var parentObject = walls.transform;
            
            foreach (var rowWall in rowWalls)
            {
                var wallVertices = new List<Vector3>
                {
                    new Vector3(rowWall.startingColumn, 0, rowWall.row),
                    new Vector3(rowWall.startingColumn, wallHeight, rowWall.row),
                    new Vector3(rowWall.endingColumn, wallHeight, rowWall.row),
                    new Vector3(rowWall.endingColumn, 0, rowWall.row)
                };
            
                var indices = new List<int>
                {
                    0, 1, 2, 2, 3, 0,
                    0, 2, 1, 3, 2, 0,
                };
            
                var mesh = new Mesh();
                mesh.SetVertices(wallVertices);
                mesh.SetTriangles(indices, 0);
                
                var wall = new GameObject("Wall");
                wall.transform.parent = parentObject;
                wall.AddComponent<MeshFilter>().mesh = mesh;
                wall.AddComponent<MeshRenderer>().material = wallMaterial;
                
                var boxCollider = wall.AddComponent<BoxCollider>();
                boxCollider.size = new Vector3(rowWall.endingColumn - rowWall.startingColumn, wallHeight, 0.1f * mapScale);
                
                wall.isStatic = true;
                wall.layer = LayerMask.NameToLayer("Wall");
            }
            
            foreach (var columnWall in columnWalls)
            {
                var wallVertices = new List<Vector3>
                {
                    new Vector3(columnWall.column, 0, columnWall.startingRow),
                    new Vector3(columnWall.column, wallHeight, columnWall.startingRow),
                    new Vector3(columnWall.column, wallHeight, columnWall.endingRow),
                    new Vector3(columnWall.column, 0, columnWall.endingRow)
                };
                
                var indices = new List<int>
                {
                    0, 1, 2, 2, 3, 0,
                    0, 2, 1, 3, 2, 0,
                };
            
                var mesh = new Mesh();
                mesh.SetVertices(wallVertices);
                mesh.SetTriangles(indices, 0);
                
                var wall = new GameObject("Wall");
                wall.transform.parent = parentObject;
                wall.AddComponent<MeshFilter>().mesh = mesh;
                wall.AddComponent<MeshRenderer>().material = wallMaterial;

                var boxCollider = wall.AddComponent<BoxCollider>();
                boxCollider.size = new Vector3(0.1f * mapScale, wallHeight, columnWall.startingRow - columnWall.endingRow);

                wall.isStatic = true;
                wall.layer = LayerMask.NameToLayer("Wall");
            }

            walls.isStatic = true;
        }

        // Creates the floor mesh.
        private void CreateFloorMesh(int rows, int columns)
        {
            var floorMesh = CreateRectangularMesh(rows, columns, mapScale, 0, true);

            floorMeshFilter.mesh = floorMesh;
            floorCollider.sharedMesh = floorMesh;
        }

        // Creates a rectangular mesh.
        private Mesh CreateRectangularMesh(
            int rectangleHeight,
            int rectangleWidth,
            float squareSize,
            float height,
            bool facingUpwards
        )
        {
            var mesh = new Mesh();

            var vertices = new Vector3[4];

            const int leftX = 0;
            var topZ = rectangleHeight * squareSize;
            var rightX = rectangleWidth * squareSize;
            const int bottomZ = 0;

            vertices[0] = new Vector3(leftX, height, topZ); //Top Left
            vertices[1] = new Vector3(rightX, height, topZ); //Top Right
            vertices[2] = new Vector3(rightX, height, bottomZ); //Bottom Right
            vertices[3] = new Vector3(leftX, height, bottomZ); //Bottom Left

            var triangles = !facingUpwards ? new[] {0, 3, 2, 2, 1, 0} : new[] {0, 2, 3, 1, 2, 0};

            mesh.vertices = vertices;
            mesh.triangles = triangles;
            mesh.RecalculateNormals();

            return mesh;
        }
        
        
        public override void ClearMap()
        {
            topMeshFilter.mesh.Clear();
            if (hasCeiling && topCollider.sharedMesh != null) topCollider.sharedMesh.Clear();
            floorMeshFilter.mesh.Clear();
            floorCollider.sharedMesh.Clear();
            foreach(Transform child in walls.transform)
            {
                Destroy(child.gameObject);
            }            
            
            var navMeshes = navMeshObject.GetComponents<NavMeshSurface>();
            foreach (var navMesh in navMeshes) Destroy(navMesh);
        }
    }
}
